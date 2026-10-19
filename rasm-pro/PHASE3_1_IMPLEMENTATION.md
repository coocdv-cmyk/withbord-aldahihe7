# Phase 3.1 — Implementation Report

Deliverable: a **visibly better rerendered WW1 film** (`projects/ww1/render/preview_v2.mp4`) produced by the
improved `rasm-pro` engine, plus all Phase-3.1 evidence. The **original v1 MP4 was lost** on 2026-10-19
(overwritten by a render that omitted `--out`); its pixels are preserved as stills and inside the diagnostic
video, and the v1 plan re-renders as `preview_v1_plan_replay.mp4`. Every other pre-existing asset/project
is untouched.

---

## 1. What changed (file manifest, all under `rasm-pro/`)

### Engine — typography & tracing
| file | change |
|---|---|
| `engine/strokes/thinning.py` | `thin()` now uses **Guo–Hall** only (`_guo_hall_counted`); `zhang_suen()` kept as comparison baseline for tests. Fixes skeleton fragmentation (RC1). |
| `engine/strokes/text_paths.py` | bidi runs + **RTL glyph emission order** (`list(reversed(gs))` for rtl runs, digits stay LTR) and **word-union tracing**: per token, glyph rasters are composed into one mask, thinned once, traced once (`_process_mask`). (RC2) |
| `engine/strokes/hand_order.py`, `engine/strokes/hand_timeline.py` | drawing order/state machine: IDLE→MOVE_TO_START→PEN_DOWN→DRAW→PEN_UP→TRAVEL→PAUSE→COMPLETE, arc-length parameterisation and velocity profile; used by the test lab and the demo tools. |
| `engine/strokes/mask_path.py` | `_Mask` incremental neighbour counts + vectorised start search (perf), plus the self-count correctness rule; `_count_neighbours` kept as reference. Output verified identical (`tools/verify_raster_equiv.py`). (RC4) |
| `engine/render/canvas.py` | `Whiteboard.paint()` breaks the polyline at every `jumps` index → no fake straight lines across pen lifts (RC3); `ImageReveal` accepts an explicit `img_box` so the reveal mask and the photo stay aligned (I2). |
| `engine/render/director.py` | `reveal_time` for image elements (default 6.0 s, I3); camera `zoom_w = clamp(bbox_w*2.6, cw*0.46, cw)`; template element dispatch; `CACHE_STATS`; image reveal passes `img_box`. |
| `engine/render/templates.py` | decorations (hand lines, arrows, marker bands, underlines, flourishes, paper cards, torn strips, tapes) + `timeline_strokes`, `bars_strokes`, `text_strokes`, `place_strokes` (natural-size placement, I4) + the 3 cinematic templates; timeline sub-label size 0.52 → **0.62** of the label size (legibility fix, film + template re-rendered). |
| `engine/audio/sfx.py` | SFX library: event → sample mapping, `build_track()` (mixing, envelope, normalisation), `mux_into()` (ffmpeg mux of the rendered video + SFX WAV, I1). |
| `engine/audio/__init__.py` | exports for the SFX layer. |

### CLI / planning
| file | change |
|---|---|
| `rasm.py` | `render` gains `--plan`, `--no-sfx`, `--sfx-preset {paper,subtle,bold}`; SFX is muxed automatically after render; `expect_audio` fixed for the post-mux validation (I5). |
| `tools/build_ww1_v2.py` | builds `plan_v2.json` from authentic script sentences with explicit line breaks, template elements and `PACING = 0.72` (scene duration = natural drawing time × 0.72). |
| `projects/ww1/storyboard/plan_v2.json` | the v2 plan (canvas 2560×1440, 24 fps, 5 scenes, 28 elements). |

### Tests / evidence tools (new)
`tests/test_mask_path_equiv.py`, `tools/repro_phase31.py`, `tools/qa_arabic.py`, `tools/perf_phase31.py`,
`tools/perf_raster_profile.py`, `tools/verify_raster_equiv.py`, `tools/make_templates_demo.py`,
`tools/make_diag_video.py`, `tools/ffprobe_report.py`.

### Assets
`assets/sfx/pen_ink.wav`, `assets/sfx/pen_felt.wav` + `assets/sfx/LICENSES.json`.

---

## 2. The improved film

- Plan: `plan_v2.json` — 5 scenes / 28 elements (text, image reveals, highlight bands, torn strips,
  underline, flourish, timeline, cards, arrows).
- Texts are the film's **authentic script sentences** (`projects/ww1/script/script.txt` lines 1–10) with
  explicit `\n` line breaks so each line matches its rect's aspect; nothing is hand-typed ad hoc.
- Pacing: scene durations = natural handwriting time × **0.72** (film 79.9 s planned / **81.5 s rendered**,
  ≈28 % faster than the natural pace; scene-level rounding accounts for the +2 %). Disclosed deliberately.
- Audio: **SFX only** (1 093 down / 1 093 up / 27 taps / 4 slides from the event stream of 2 229 pen
  events) — **there is no narration for ww1 and none was invented**.
- Command (always pass an explicit `--out`):

```powershell
$env:PYTHONUTF8='1'
.venv\Scripts\python.exe rasm.py render ww1 --plan plan_v2.json --size 1280x720 --fps 24 --out projects\ww1\render\preview_v2.mp4
```

- Result (FFprobe, `qa/phase31_ffprobe.txt`): h264 1280×720 24 fps, 1956 frames, 81.5 s, yuv420p,
  AAC 48 kHz mono 81.49 s, duration delta 0.007 s, 29 957 725 bytes. Render wall time **173.0 s** after the
  sub-label change (an earlier warm-cache render took 90.9 s, ≈21.5 fps effective).

## 2b. Incident disclosure — the original v1 MP4 was overwritten

During the final re-render (after the timeline sub-label legibility fix), a render command was issued
without `--out`. The engine wrote its default target and **overwrote `projects/ww1/render/preview.mp4`**
(the original 1069-frame / 44.541667 s v1 baseline). No copy existed elsewhere on the machine (bounded
search of `%TEMP%`, `%APPDATA%`, `studio/outputs`, `test/`).

Mitigations performed (see `qa/phase31_repro/before/film_v1_stills/README.md`):

1. The improved film was re-rendered with an explicit `--out` and validated
   (`projects/ww1/render/preview_v2.mp4`, 1956 frames, 81.5 s, FFprobe PASS).
2. The original v1 pixels are preserved: 10 full frames + 5 zoom crops in
   `qa/phase31_repro/before/film_v1_stills/`, the 6 stills in `qa/phase31_repro/before/film/`, and the
   three "قبل" film pairs inside `qa/phase31_diag/before_after.mp4` (extracted before the overwrite).
3. The v1 **plan** was never modified: `projects/ww1/storyboard/plan.json` still renders end-to-end —
   `projects/ww1/render/preview_v1_plan_replay.mp4` is that untouched plan re-rendered with the
   Phase 3.1 engine (1039 frames, 43.29 s, no audio), i.e. the old layout with corrected typography.
4. Every command in §7 now passes an explicit `--out`.

Consequence for "the original is recoverable": the original **plan** is recoverable and re-rendered, and the
original **pixels** are preserved as frames and inside the diagnostic video, but the original MP4 file
itself no longer exists. This is also stated in `PHASE3_1_REVIEWS.md` and in `PHASE_3_1_STATUS.md`.

## 3. Cinematic templates (mandatory 3, with real clips)

| template | clip | contents |
|---|---|---|
| PREMIUM WHITEBOARD | `qa/phase31_templates/premium_whiteboard.mp4` (28.5 s) | curved display title, marker highlight, taped photo card, hand arrow at the end, underline, SFX |
| DOCUMENTARY PAPER COLLAGE | `qa/phase31_templates/documentary_collage.mp4` (29.29 s) | taped photo cards, torn paper strips, red underline, closing statement strip, SFX |
| TIMELINE / DATA STORY | `qa/phase31_templates/timeline_data_story.mp4` (26.58 s, 638 f) | axis + 3 bars with values and year labels (natural-size labels), SFX |

All three are Arabic-capable (rendered here with Arabic labels), implemented as director element types in
`engine/render/templates.py` and driven by `tools/make_templates_demo.py`:

```powershell
$env:PYTHONUTF8='1'; .venv\Scripts\python.exe tools\make_templates_demo.py
```

## 4. SFX pipeline and licensing

- Event mapping: pen events (`down`/`up`/`tap`/`slide`) are emitted by the director per frame
  (`preview_v2.sfx.json`, 2 220 events) and rendered by `engine/audio/sfx.py::build_track` into
  `preview_v2.sfx.wav`; `mux_into` then merges video + SFX into a single MP4.
- Sources: `pen_ink.wav` and `pen_felt.wav` are **public-domain recordings** (`PDSounds #179/#180` by
  *stephan*, 2007, PD-Sound), fetched from Wikimedia Commons; recorded in `assets/sfx/LICENSES.json`.
  Paper-slide sounds are **procedurally generated** (no recording available in the free set) and that fact
  is recorded in the same file and in this report.
- Mixing: per-event gain, 12 ms attack/30 ms release envelopes, peak-safe normalisation (no clipping).
- Audio mode for ww1: **SFX only**; `--no-sfx` disables it, `--sfx-preset {paper,subtle,bold}` changes
  intensity.

## 5. Acceptance checklist → evidence map

| acceptance item | status | evidence |
|---|---|---|
| Arabic spacing/crowding visibly fixed | ✔ | `qa/phase31_repro/{before,after}` (pieces 1338→56, 1410→178, 225→32, 1614→73) + film frames |
| RTL correctness | ✔ | `rtl_start_ok = 1.0` (104 cases), `digits_ltr_first_stroke_left = true`, order maps |
| Pen lifts/pauses natural | ✔ | `teleports = 0` everywhere, J group 14 downs/14 ups, word-union lifts only at gaps/dots |
| Final Arabic matches the shaped reference | ✔ | lab `cov_struct ≥ 0.974`, `prec_tol ≥ 0.9491`, `skel_near_ref = 1.0` |
| Improved film rerendered, original recoverable | ✔ | `preview_v2.mp4` (new) + v1 pixels preserved as stills + diagnostic video; v1 plan re-renders as `preview_v1_plan_replay.mp4` (the original MP4 was overwritten — disclosed in `PHASE3_1_REVIEWS.md` §"Incident") |
| FFprobe-validated | ✔ | `qa/phase31_ffprobe.txt` (film, clips, diagnostic video, SFX) |
| Before/after evidence | ✔ | stills + `qa/phase31_diag/before_after.mp4` |
| ≥ 20 Arabic word tests | ✔ | 104 letter/word cases (30 letters + 68 words + 6 diacritic) |
| Old 22 passing tests are not the evidence | ✔ | new 145-case lab + 5 equivalence tests + perf benchmarks |
| 3 cinematic templates with real clips | ✔ | §3 |
| Real SFX (or disclosed procedural) | ✔ | §4 |

## 6. Preservation & non-goals

- No legacy `studio` renderer was merged or rebuilt; `rasm-pro` Director remains the only film engine.
- No new frameworks, paid APIs or downloads: `uharfbuzz`, `fontTools`, `opencv`, `scipy`, `numpy`, `Pillow`
  were already in the environment; FFmpeg/FFprobe are the bundled `studio/runtime` 9.0.2 binaries.
- All pre-existing tests still pass (24/24), all user projects/assets/scripts untouched; `cache/strokes/`
  documents remain valid (the optimisation is output-identical).
- Not done (documented as limitations): calligraphic per-glyph stroke order, animated camera rotation,
  sub-pixel brush textures from real ink photos.

## 7. Reproduce everything (exact commands, `rasm-pro` root)

```powershell
$env:PYTHONUTF8='1'
.venv\Scripts\python.exe tools\run_tests.py                       # 24/24
.venv\Scripts\python.exe tools\qa_arabic.py                       # 145 cases → qa\phase31_lab
.venv\Scripts\python.exe tools\repro_phase31.py --tag after       # defect metrics
.venv\Scripts\python.exe tools\perf_phase31.py thinning           # perf: thinning + raster
.venv\Scripts\python.exe tools\perf_phase31.py text               # perf: cold/warm text
.venv\Scripts\python.exe tools\perf_phase31.py scene              # perf: cold/warm scene prep
.venv\Scripts\python.exe tools\perf_raster_profile.py             # cProfile of the tracer
.venv\Scripts\python.exe tools\verify_raster_equiv.py             # bit-identical trace check
.venv\Scripts\python.exe tools\build_ww1_v2.py                    # rebuild plan_v2.json
.venv\Scripts\python.exe rasm.py render ww1 --plan plan_v2.json --size 1280x720 --fps 24
.venv\Scripts\python.exe tools\make_templates_demo.py             # 3 template clips
.venv\Scripts\python.exe tools\make_diag_video.py                 # before/after video
.venv\Scripts\python.exe tools\ffprobe_report.py                  # qa\phase31_ffprobe.txt
```
