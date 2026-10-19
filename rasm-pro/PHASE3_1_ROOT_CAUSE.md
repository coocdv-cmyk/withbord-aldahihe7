# Phase 3.1 — Root Cause Analysis (Arabic handwriting & typography)

Scope: `rasm-pro` whiteboard engine (`engine/strokes/*`, `engine/render/*`), the ww1 project, and the
Phase 3.1 acceptance defects reported by the user:

> حروف متلاصقة/عالقة، وقفات ورفعات قلم غير طبيعية، بدايات خاطئة، أشكال حروف غير دقيقة، ومظهر «مولّد تقنيًا».

All numbers below are produced by committed tools and stored as machine-readable artifacts:

| Tool | Artifact |
|---|---|
| `tools/repro_phase31.py --tag before\|after` | `qa/phase31_repro/{before,after}/diagnostics.json` + draw/order PNGs |
| `tools/qa_arabic.py` | `qa/phase31_lab/report.json`, `summary.md`, group mosaics |
| `tools/perf_phase31.py` | `qa/phase31_perf/perf.json` |
| `tools/run_tests.py` | 24 test results (console) |
| `tools/verify_raster_equiv.py` | bit-identical raster-trace verification |

---

## RC1 — Zhang–Suen thinning fragments thin curves (the real cause of "stuck / crowded letters")

**Symptom.** Letters looked *stuck together*, with small "chips" left behind after the pen passed, and
the draw sequence contained hundreds of micro-pieces per line.

**Cause.** `engine/strokes/thinning.py` used **Zhang–Suen** thinning. ZS deletes pixels in two sub-iterations
using local 2×3/3×2 patterns; on thin, anti-aliased curves (Arabic diagonals, letter bowls, connector
strokes) it **erodes pixels it cannot restore**, splitting one connected glyph into many 8-connected
islands. Each island is later traced as a separate pen stroke/subpath.

**Fix.** `thin()` now calls `_guo_hall_counted` (Guo–Hall) only. Guo–Hall uses a rotation-invariant
pattern set and preserves 8-connectivity on the same masks. `zhang_suen()` is kept (unused by the
pipeline) for comparison tests.

**Measured (`tools/perf_phase31.py thinning`).**

| mask | px | Zhang–Suen | components | Guo–Hall | components |
|---|---|---|---|---|---|
| ring, 5 px stroke | 2 104 | 0.0042 s · 3 iters | **60** | 0.0053 s · 4 iters | **1** |
| word «الحرب» 190 pt | 9 629 | 0.1422 s · 7 iters | **152** | 0.2733 s · 10 iters | **1** |

Cost: Guo–Hall is ≈1.3–1.9× slower than ZS on the same mask. This was acceptable: at diagnosis time
thinning was 1.3 % of the raster pipeline; after RC4 (below) it is ≈17 % of `raster_to_strokes`
(1.42 s of 8.56 s) — still not the bottleneck.

**Effect on the film (`qa/phase31_repro`, element-level, before → after).**

| target (plan.json element) | strokes | subpaths (polyline pieces) |
|---|---|---|
| s1-title «في صيف عام 1914، اشتعلت الحرب…» | 33 → 6 | **1338 → 56** |
| s1-sub (body line, amiri) | 72 → 14 | **1410 → 178** |
| s2-tag «معركة السوم» (cairo) | 10 → 2 | **225 → 32** |
| s3-title «في عام 1917، دخلت الولايات المتحدة الحرب…» | 55 → 9 | **1614 → 73** |

Subpath counts drop by **20–24×**: the pen now draws a letter/word in a few continuous pieces instead
of hundreds of chips. This is the direct fix for "حروف متلاصقة/عالقة" and for the "technically generated" look.

---

## RC2 — HarfBuzz RTL buffer is visually left-first; a word must be drawn right→left (and as one unit)

**Symptom.** Wrong start positions; words drawn as disjoint glyph pieces in the wrong direction; the pen
often "jumped back" to the left end and ate into already-drawn letters.

**Cause (two layers).**
1. `uharfbuzz` returns shaped glyphs in **visual order, left-most first**, even for RTL runs. The old
   code emitted glyphs in buffer order, i.e. the left end of an Arabic word was drawn first.
2. Traces were produced **per glyph**, so one Arabic word (which is one connected script unit) became
   N separate strokes with N pen lifts.

**Fix (`engine/strokes/text_paths.py`).**
1. Bidi runs are classified (`_bidi_runs`, `_resolve_neutrals`, `_char_class`), then per run:
   `glyph_iter = list(reversed(gs)) if d == "rtl" else list(gs)` — RTL runs are emitted **right→left**,
   LTR runs (digits, Latin) stay left→right. Digit check: `digits_ltr_first_stroke_left = True`
   (`qa/phase31_lab/report.json`).
2. **Word-union tracing**: for a token, all its glyph rasters are composed into **one mask**, thinned
   **once** (`_process_mask`), then traced by `order_mask_paths(mask, rtl=True)`, which picks the
   **right-most terminal** of the right-most component (`pick_start`: `max(pool, key=lambda p: (p[1], -p[0]))`)
   and walks the skeleton with a direction-continuity rule (prefer reversing direction, then right/down/left/up).
   Pen lifts now exist **only at real script gaps and dots**.

**Note on a stricter diagnostic.** The repro tool also reports `starts_rightmost_ratio` (first point in the
right-most 30 % of the stroke bbox): 0.833–1.0 after the fix. Values below 1.0 are caused by closed-loop
initial letterforms (e.g. the head of «م») whose extreme right ink has **no skeleton terminal**; the trace
therefore starts at the nearest terminal (still at the right side of the word). The authoritative,
documented metric is the QA-lab `rtl_start_ok` = "first traced point lies in the **right half** of the
stroke's own bbox": **1.0 on every RTL stroke of groups A–F and group K** (K = the film's ten texts verbatim);
0.976 for the long-text case (41 strokes, group H).

**Word order.** Connected components ("bodies") are processed `bodies.sort(key=lambda cp: -cx_of(cp))` —
right-most body first; dots are drawn after their body (`dots.sort(key=(-cx, cy))`), so kashida-like
long connectors are never drawn before the letters they connect.

---

## RC3 — `Whiteboard.paint()` concatenated segments across pen-lift jumps (artificial straight lines)

**Symptom.** Occasional **long straight lines** slicing across letters (visible immediately after a letter
finished); the pen "tore" through the word.

**Cause.** The frame painter flattened each stroke into one polyline and painted `p_i → p_{i+1}` for every
consecutive pair, ignoring the stroke's `jumps` index set (subpath boundaries = pen lifts). A jump from the
end of one subpath to the start of the next was painted as a solid segment.

**Fix (`engine/render/canvas.py`).** `Whiteboard.paint()` breaks the polyline at every jump index
(`i in jumps` ⇒ skip that segment); `DocCursor.advance()` reports subpath transitions accordingly. A lift is
now a real lift: the pen travels without ink.

**Measured.**

| case | teleports > 3 px (before → after) |
|---|---|
| s2-tag «معركة السوم» | **2 → 0** (worst before: 13.0 px straight line `[1982.7, 286.7] → [1995.5, 284.4]`, plus 5.9 px) |
| s1-title / s1-sub / s3-title | 0 → 0 |
| QA lab (all 145 cases) | `teleports_total = 0` |

Visual proof: `qa/phase31_repro/before/draw_s2-tag_020.png` (oblique line through the letters) vs
`after/draw_s2-tag_020.png` (clean partial word, no line), and the same pair for every case inside
`qa/phase31_diag/before_after.mp4`.

---

## RC4 — Neighbour-counting walker was the performance wall (fixed without changing output)

**Cause.** `generate_mask_path()` (photo raster tracing) called `_count_neighbours()` for every candidate
step; cProfile measured **47.5 M calls / 87.3 s** of a 118.9 s run, plus a full-array start-point scan per
trace (110.7 s cumulative in `_find_start_point`).

**Fix (`engine/strokes/mask_path.py`).** `class _Mask` maintains for every pixel an incrementally-updated
count of set 8-neighbours (O(1) clear/update, vectorised construction) and `_find_start_point` uses
`np.nonzero` instead of a Python scan. `_count_neighbours` is kept as the reference implementation used by
the equivalence tests.

**Critical correctness detail.** During tracing the mask pixel `current` is cleared *before* its neighbour
count is read (the count controls `last_good`). The first implementation zeroed the count of the cleared
pixel itself, which is wrong: a pixel is not its own neighbour, so its count must stay unchanged when it is
cleared. `_Mask.clear()` now decrements only the 3×3 neighbourhood and adds the self-decrement back:
`self.cnt[y, x] += 1`.

**Equivalence evidence (mandatory — cached documents and the rendered film derive from this code).**
- `tests/test_mask_path_equiv.py` (5 tests): ring, open stroke, 6 random blobs, real Arabic word
  («الحرب», Guo–Hall), real photo trace at 1/6 scale — reference vs optimised walker, exact equality.
- `tools/verify_raster_equiv.py`: the three real ww1 images re-traced from scratch and compared to the
  on-disk cached documents produced by the old algorithm → **bit-identical**: `c75888b731eb.jpg`
  819 strokes / 33 706 points, `a21b49758ec5.jpg` 14 strokes / 2 402 points, `6aee608a669e.jpg`
  140 strokes / 3 624 points (points, lengths, brush, brush profile, jumps, kind, color, meta).
- Result: 15× faster trace (111.4 s → 7.39 s on the 900 px photo), output unchanged ⇒ **the already
  rendered `preview_v2.mp4` remains valid**.

---

## Integration defects found and fixed during Phase 3.1

| # | Defect | Evidence | Fix |
|---|---|---|---|
| I1 | **SFX never muxed**: `mux_into()` built an ffmpeg command with `-map 1:a` but never added the SFX WAV as input #1 → "Invalid input file index: 1" | `qa/phase31_ww1v2_render_log.txt` (pre-fix attempt), now: v2 film has `aac 48 kHz` | add the SFX WAV as input, `-shortest`, loudness-safe mix |
| I2 | **Image reveal misalignment**: the trace was aspect-fitted to the element rect while the photo itself was stretched to it → traced ink and image edges drifted apart (poster/tank cards) | poster `6aee608a669e.jpg` 465×715 vs rect | reveal uses an explicit `img_box` (same aspect-fit math as the trace), director passes it (`director.py`, `ImageReveal(img, strokes, rect, img_box=box)`) |
| I3 | **Image reveal duration** derived from stroke length ("natural" writing time) → scene 4 alone ballooned to ≈292 s | render logs | fixed `reveal_time` per element (default 6.0 s), overridable in the plan |
| I4 | **Timeline / bars labels upscaled** (`place_strokes` scaled label strokes from a tiny natural box to the whole bar) → pixelated labels | `qa/phase31_templates/tl_sheet2.jpg` before/after | labels placed at **natural document size** (pass `doc.width/height`, no scaling); re-rendered clip verified clean |
| I5 | **`validate_video` false failure after SFX mux**: `expect_audio` was computed before muxing | v2 validation log | `rasm.py` sets `expect_audio = bool(audio_file) or sfx_muxed` |

---

## What was deliberately *not* done

- No writing order derived from bounding boxes: order comes from the shaped glyph order (bidi runs) and the
  skeleton walk with direction continuity.
- No blind reversal of SVG paths. `scan_svg` output keeps authored path order; RTL handling happens at the
  text-shaping layer only.
- No merge/rebuild of the legacy `studio` renderer; `rasm-pro` Director stays the only film engine.
- The original film `projects/ww1/render/preview.mp4` (v1) was **lost** on 2026-10-19 (overwritten by a render
  that omitted `--out`); its pixels are preserved in `qa/phase31_repro/before/film/` and
  `qa/phase31_repro/before/film_v1_stills/`, and inside `qa/phase31_diag/before_after.mp4`. The v1 plan
  re-renders as `projects/ww1/render/preview_v1_plan_replay.mp4`.

## Residual root-cause limitations (disclosed, not defects)

1. **Within-glyph order is geometric, not calligraphic.** A word is traced as one skeleton: start at the
   right-most terminal, continue with direction continuity. This yields natural-looking, lift-free words, but
   it is *not* the canonical stroke order a trained hand writer uses (e.g. drawing the head of «م» before its
   tail). A calligraphic order needs authored centerline data per glyph — out of scope for this phase.
2. **Closed-loop initials** cannot start at the extreme right pixel (no terminal there), see RC2 note.
3. **Photo reveals are skeleton traces** of dark content (fattened brush) — an intentional "torn archive
   cutout" look, not a pixel-accurate image draw-on.
4. ZS thinning remains in the module (unused) as the comparison baseline for the test suite.
