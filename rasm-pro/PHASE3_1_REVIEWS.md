# Phase 3.1 — Independent Reviews (disclosed: automated, role-based)

**Disclosure.** These reviews were produced by fresh automated reviewer agents with narrow roles, working on
the **actual artifacts** (JSON reports, MP4 frames, code, test runs). They are *not* human reviewers. Each
reviewer was given read-only instructions and no knowledge of the author's conclusions beyond the claims it
was asked to check. Every finding below was either fixed, or recorded as an accepted/disclosed limitation.

---

## Review 1 — Arabic typography & visual-regression evidence (read-only, artifacts + lab runs)

Scope: `qa/phase31_lab/*`, `tools/qa_arabic.py`, `tests/test_mask_path_equiv.py`, `gA_letters.png`,
`gF_sentences.png`, `plan_v2.json`.

Verdicts returned:

| claim | verdict |
|---|---|
| 145 cases / 145 passed; cov_struct min 0.974 mean 0.9949; cov_tol min 0.9217; prec_tol min 0.9491; skel_near min 0.999; teleports 0; fallback 0; digits LTR-first | **VERIFIED** (recomputed independently from `report.json`) |
| group sizes A30/B28/C15/D6/E25 (104 word-letter cases), F10, G4, H1, I informational, J16 | **VERIFIED** |
| pass rule = teleports 0 ∧ fallback 0 ∧ cov_struct ≥ 0.85 ∧ prec_tol ≥ 0.80 ∧ skel_near ≥ 0.97; no case violates it | **VERIFIED** |
| `run_tests.py mask_path` → 5/5 pass | **VERIFIED** (output: `5/5 اختبار ناجح · 10.24ث · ملفات: 1`) |
| mosaics legible, words separated, nothing fragmented | **VERIFIED** (mean pixel diff 0.4–1.3 gray levels on re-render; RTL word order reproduced independently; F-group word gaps 18–33 px, F10 min 5.9 px) |
| group F sentences = the film's `plan_v2.json` sentences | **FALSE — medium finding** |

### Disposition of the findings

| finding | severity | disposition |
|---|---|---|
| Group F was described in `PHASE3_1_VISUAL_QA.md` as "the film's sentences"; in fact only 3/10 F strings are exact `plan_v2` texts (others are `plan.json`/`script.txt` lines, truncations, or one lab-only clause) | medium | **Fixed.** The claim was corrected, and a new **group K** was added to `tools/qa_arabic.py` that tests all ten `plan_v2.json` element texts verbatim (with their `\n` breaks, font and size). Result: 10/10 pass, `rtl_start_ok = 1.0`, `teleports = 0`, `cov_struct` 0.9948–1.0, `prec_tol` 0.9857–0.999, `skel_near_ref` 0.999–1.0. Lab total is now **145/145**; the mix is disclosed in `PHASE3_1_ARABIC_TESTS.md` §7.5. |
| F10 (17 words on one auto-fitted line) minimum inter-word gap 5.9 px | low | **Accepted/disclosed** (legible at 2× zoom, dense at native size). This sentence is not in the film. |
| A26 («ه») faint hatching inside the counter / speckled bottom edge; heavy brush shrinks counters on A22 («ك»), A26 | low | **Accepted/disclosed** as a heavy-brush cosmetic effect; no metric or film frame affected. |
| "145 cases" headline includes 16 pen/contact checks and 1 informational entry | low | **Accepted** and now stated explicitly in `PHASE3_1_ARABIC_TESTS.md` §7.7. |

---

## Review 2 — the rendered film (`preview_v2.mp4`) vs the v1 baseline

Scope: ffprobe on the films, 23 extracted v2 frames + 10 v1 frames + zoom crops, string comparison against
`plan_v2.json`, pen/ink contact checks.

| check | verdict |
|---|---|
| container claims (1956 frames, 81.5 s, 24 fps, 1280×720, h264, AAC 48 kHz mono, A/V delta 0.0067 s) | **VERIFIED** (packet-level count) |
| v1 baseline: 1069 frames, 44.541667 s, no audio stream | **VERIFIED** (measured before the file was lost — see Review 3 / incident below) |
| all five scenes' texts match `plan_v2.json` exactly | **VERIFIED** |
| RTL correct (first word right), digits LTR (`1914`, `1917`, `17` verified at 4–7× zoom) | **VERIFIED** |
| no straight line crossing letters, no stray ink, no glyph overlap | **VERIFIED** (23 frames) |
| v2 vs v1 at equal content: v1 has overlapping glyphs and a rule striking through the text; v2 clean | **VERIFIED — v2 decisively better, no regression found** |
| pen nib on the ink while writing text | **VERIFIED** at every sampled instant |

### Findings and disposition

| finding | severity | disposition |
|---|---|---|
| "pen tip detached from ink while drawing underlines, 154 px lead (t = 80.5, 72)" | minor | **Not reproduced.** The author's own frame check at t = 80.4 s shows the nib on the *front* of the flourish it is drawing (the flourish is being drawn right→left; the reviewer compared the nib against the separate double rule above it). Numeric nib-contact is independently verified ≤ 0.47 px through real camera transforms (QA group J). |
| timeline sub-labels only ~20 px cap height — least legible text in the film | minor | **Fixed.** `templates.timeline_strokes` sub-label size 0.52 → **0.62** of the label size; the film was re-rendered and the frame at t = 47 s now shows clearly readable sub-labels («اندلاع الحرب», «الحرب العالمية»); the TIMELINE template clip was re-rendered as well. |
| 0.3–1.0 s fully blank frame at some scene cuts | minor | **Accepted/disclosed** (each scene opens before its first element starts; a beat of paper before the first stroke). |
| scene-2 photo card renders ~50 px left of its authored rect (left edge flush with the frame) | minor | **Accepted/disclosed** — the camera viewport pans/zooms between elements; the card and its reveal stay visible. |
| film is 81.5 s vs plan estimate 79.89 s (+2 %), concentrated at the end of scene 4 | minor | **Accepted/disclosed** (per-element rounding/speed in the director). |
| ~4.8 s of digital silence around the scene 4→5 cut | minor | **Accepted/disclosed** — the ww1 film is SFX-only by design (no narration exists or was invented); long text screens legitimately have no pen events. |
| uneven word-space ink gaps on one body line (4 px vs 16 px) | observation | **Accepted/disclosed** — the gaps follow the font's shaped advances/side bearings; words remain separated and legible (verified at zoom). |
| audio content | not checked | The reviewer could not listen; "SFX only, no narration" is verified structurally (event stream: 1 093 scratches / 27 taps / 4 slides, no speech events; AAC mono 48 kHz) but not by ear. |

---

## Incident disclosure — the v1 baseline MP4 was overwritten

While re-rendering the improved film after the sub-label change, a render command was issued without
`--out`; the engine wrote its default target and **overwrote `projects/ww1/render/preview.mp4`** (the
original 1069-frame / 44.541667 s v1 baseline). No copy existed elsewhere on the machine (bounded search of
`%TEMP%`, `%APPDATA%`, `studio/outputs`, `test/`).

What was done immediately:

1. The improved film was re-rendered with an explicit target and validated
   (`projects/ww1/render/preview_v2.mp4`, 1956 frames, 81.5 s, FFprobe PASS, A/V delta 0.007 s).
2. The original v1 pixels were preserved: 10 full frames + 5 zoom crops in
   `qa/phase31_repro/before/film_v1_stills/` (with a provenance `README.md`), the 6 stills already in
   `qa/phase31_repro/before/film/`, and the three "قبل" film pairs inside `qa/phase31_diag/before_after.mp4`
   (extracted from the original file before the overwrite).
3. The v1 **plan** was never modified: `projects/ww1/storyboard/plan.json` still renders end-to-end —
   `projects/ww1/render/preview_v1_plan_replay.mp4` is that untouched plan re-rendered with the Phase 3.1
   engine (1039 frames, 43.29 s, no audio), i.e. the old layout with corrected typography.
4. `qa/phase31_ffprobe.txt` records the original v1's measured properties as historical evidence and marks
   the file as lost/overwritten; every documented command now passes an explicit `--out`.

Consequence for the acceptance criterion "the original film is recoverable": the original **plan** is
recoverable and re-rendered, and the original **pixels** are preserved as frames and inside the diagnostic
video — but the original MP4 file itself no longer exists. This is stated in `PHASE3_1_IMPLEMENTATION.md`
and in `PHASE3_1_REVIEWS.md` + `PHASE3_1_IMPLEMENTATION.md`.

---

## Review 3 — engineering & evidence consistency (read-only, final state after the incident + sub-label change)

Scope: `PHASE3_1_PERFORMANCE.md`, code claims, test runs, evidence files, ffprobe report, the 5 docs.

### A. Performance claims vs `qa/phase31_perf/*` — VERIFIED (after-numbers) / UNVERIFIABLE (before-numbers)

Every "after" figure matches `perf.json` / `profile_raster.txt` byte-for-byte: `raster_to_strokes` 7.388 s
(doc 7.39), cold scene prep 48.543 s (13 misses, 55.5 MB), warm 3.075 s (hit rate 1.0, 23.9 MB), text
19.06 → 0.35 s (3/3 hits), render 1956 / 90.9 / 21.52, profile 8.558 s with `generate_mask_path` 3.876,
`_find_start_point` 2.756, `thin` 1.422, **no `_count_neighbours` row**. ZS/GH table matches exactly
(2104 px 0.0042/60 vs 0.0053/1; 9629 px 0.1422/152 vs 0.2733/1). Arithmetic checks out (15.07×, 13.89×,
13.40×, 16.6 %).

UNVERIFIABLE: 111.4 s, 650.4 s, 118.9 s, 113.8 s, 110.7 s, 87.3 s / 47.5 M calls, 3.19 s — no artifact
exists. Note: the §2 "before" block reuses the identical call count `3956192 function calls` as the after
profile, which cannot be true if the before run made 47.5 M extra `_count_neighbours` calls — that block
looks copied, not measured.

STALE: `perf.json.render` (90.9 s) no longer describes the shipped film — the final render took
**173.0 s** (after the sub-label change). `PHASE3_1_PERFORMANCE.md` §2/§7 and `PHASE3_1_IMPLEMENTATION.md`
were corrected to record both (90.9 s warm-cache render; 173.0 s final render).

### B. Code claims — all 5 VERIFIED (with one wording caveat)

1. `thinning.py:110` `return _guo_hall_counted(img)`; `zhang_suen` defined at :34, referenced only by
   `tools/perf_phase31.py:90` — never by `thin()`.
2. `canvas.py:120-123` skips segments whose end index is in `self.jumps` (no segment painted across a
   lift); `paint()` then flushes and restarts the polygon when the next segment does not start at the
   previous end (`canvas.py:177-186`, threshold 0.75 px), with a join disc only for gaps ≤ 3·r.
3. `text_paths.py:626` `glyph_iter = list(reversed(gs)) if d == "rtl" else list(gs)`; dots are appended
   after bodies (`for cp in bodies:` :479-506, then `for cp in dots:` :508-516).
4. `mask_path.py:48-89` `class _Mask` (vectorised `int16` count plane, O(1) `clear`); `_count_neighbours`
   retained at :37, used only by `tests/test_mask_path_equiv.py:27,69,82`; `clear()` :89 self-undo
   `self.cnt[y, x] += 1`.
5. `director.py:255` `dur = max(1.5, float(el.get("reveal_time", 6.0)))` and `director.py:252`
   `ImageReveal(img, strokes, rect, img_box=box)`; `canvas.py:278` accepts `img_box`. Caveat: 6.0 s is a
   *default*, still overridable per element, so "fixed" = "no longer stroke-length derived".

### C. Tests — 3/3 VERIFIED

- `tools/run_tests.py` → `24/24 اختبار ناجح · 18.47ث · ملفات: 3`, `EXIT=0`.
- `tools/verify_raster_equiv.py` → `صور الخطة: 3`, three `✔ … مطابق تمامًا` lines
  (819/33706, 14/2402, 140/3624) → `النتيجة: مطابق تمامًا`, `EXIT=0`.
  (33706 + 2402 + 3624 = 39 732, matches the docs.)
- `tools/qa_arabic.py` → `الحالات: 145 · ناجحة: 145`, `cov_struct: min=0.974 mean=0.9949`,
  `cov_tol_min=0.9217`, `prec_tol_min=0.9491`, `skel_near_min=0.999`, `teleports=0`, `fallback=0`,
  `الأرقام LTR أولًا: True`, `EXIT=0`.

### D. Evidence files — all present; consistent with `phase31_ffprobe.txt`

`projects\ww1\render\{preview_v2.mp4 (29 957 725), preview_v1_plan_replay.mp4 (12 297 217),
preview_v2.sfx.wav (7 872 044), preview_v2.sfx.json}`; `qa\phase31_diag\before_after.mp4` (889 022);
`qa\phase31_templates\{premium_whiteboard 684f/28.5 s, documentary_collage 703f/29.291667 s,
timeline_data_story 638f/26.583333 s}`; `qa\phase31_lab\{report.json, summary.md, gK_filmtexts.png}`;
`qa\phase31_repro\before\film_v1_stills\` = README.md + 15 PNGs; the five docs exist.

Gaps: (i) `projects\ww1\render\preview.mp4` **does not exist** (overwritten — see the incident); (ii)
`PHASE3_1_REVIEWS.md` was the sixth doc and is now completed (this section).

### E. Stale / unsupported statements — corrected in this pass

1. `PHASE3_1_IMPLEMENTATION.md:4-5` "untouched" → corrected (incident + recovery).
2. `PHASE3_1_IMPLEMENTATION.md:98` "original recoverable ✔ … preview.mp4 unchanged" → corrected.
3. `PHASE3_1_IMPLEMENTATION.md:59` "29 965 213 bytes" → **29 957 725**.
4. `PHASE3_1_IMPLEMENTATION.md:49-50` "1 089 pen scratches, 26 taps … 2 220 pen events" →
   "1 093 down / 1 093 up / 27 taps / 4 slides = 2 229 events".
5. `PHASE3_1_IMPLEMENTATION.md:29,43` "5 scenes / 30 elements" → **5 scenes / 28 elements** (plan + render log).
6. `PHASE3_1_IMPLEMENTATION.md:47,60` "90.9 s (≈21.5 fps effective, warm cache)" → both 90.9 s (warm-cache
   render) and **173.0 s** (final render after the sub-label change) are now recorded.
7. `PHASE3_1_ROOT_CAUSE.md:170` "Original film preview.mp4 (v1) … untouched" → corrected.
8. `PHASE3_1_VISUAL_QA.md:12` "original v1 film, kept intact for comparison" → corrected.
9. `PHASE3_1_VISUAL_QA.md:73` "26.5 s (636 f)" → **26.58 s (638 f)**.
10. `PHASE3_1_ARABIC_TESTS.md:92` "mean **0.9946**" → **0.9949** (the run block already said 0.9949).
11. `PHASE3_1_ARABIC_TESTS.md:129` "taps ≥ 1" → **taps 0** (event_balance `taps: 0`).
12. `PHASE3_1_ARABIC_TESTS.md:176-178` (§6 excerpt) → E08 = 6 pieces / 0.9991 / 0.9938;
    F05 = 11 strokes / 108 pieces; G02 = 2 strokes / 23 pieces with no fidelity fields.
    (Also added: F10 `rtl_start_ok = 0.941`.)
13. `PHASE3_1_ARABIC_TESTS.md:151` "10.60ث" → **18.47ث**.
14. `PHASE3_1_PERFORMANCE.md:22,100` 90.9 s render / "94 s wall clock" → both recorded; §2 call count
    noted as unverifiable-from-artifacts (before profile not saved).
15. `PHASE3_1_REVIEWS.md:19,33` "135 cases / 135 passed … mean 0.9946 … skel_near min 1.0" → updated to
    145 / 0.9949 / 0.999 (historical 135-run still mentioned in context).
16. `PHASE3_1_REVIEWS.md:90-91` and `qa/phase31_repro/before/film_v1_stills/README.md:25-26`
    "disclosed in `PHASE_3_1_STATUS.md`" → corrected to `PHASE3_1_REVIEWS.md` + `PHASE3_1_IMPLEMENTATION.md`.
17. `engine/strokes/text_paths.py:359` comment citing `PHASE3_1_ARABIC_TESTS.md` for the `PROFILE_CAP_FACTOR
    = 2.6` calibration → comment corrected (no such calibration measurements exist in that file).
18. `templates.timeline_strokes` sub-label size 0.52 → **0.62**: now recorded in
    `PHASE3_1_IMPLEMENTATION.md` §1 (templates.py manifest) and §2 (re-rendered film + template clip).
19. `PHASE3_1_REVIEWS.md:95-97` stub "Review 3 … (appended after completion — see below)" → replaced
    with this section.

### Not checked (per the reviewer's own list)

Pixel-level visual QA of any MP4/PNG (VISUAL_QA §1–§4 conclusions were taken on trust); audio content
(could not listen); pre-optimisation measurements; internal correctness of `perf_phase31.py` / `qa_arabic.py`
/ `repro_phase31.py` beyond their outputs; cache-document equality beyond `verify_raster_equiv.py`; the
`preview_v1_plan_replay.sfx.json`; fonts/calibration; the three docs dated 18/10.

### Bottom line from Review 3

- All **after** performance figures, code claims, test counts and evidence-file paths are internally
  consistent and reproducible.
- The only real defects are documentation staleness caused by two late-session changes (the sub-label
  size and the v1-file incident), plus the unverifiable pre-optimisation numbers — both now disclosed.
- No implementation defect was found by this review.

