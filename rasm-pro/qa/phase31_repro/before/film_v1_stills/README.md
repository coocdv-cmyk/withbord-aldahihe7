# Original v1 film — preserved frames (provenance)

These PNGs were extracted from the **original baseline film** `projects/ww1/render/preview.mp4`
(h264 · 1280×720 · 24 fps · 1069 frames · 44.541667 s · 11 434 110 bytes · no audio stream) at the
timestamps in each filename (`v1_<seconds>.png`), plus the zoom crops `z_v1_*` used to inspect the v1
typography defects (overlapping glyphs, a rule striking through the text, clipped poster card).

**Disclosed incident (2026-10-19 14:31):** while re-rendering the improved film after enlarging the
timeline sub-labels, a render command was run without `--out`, so the engine wrote its default output
`preview.mp4` and **overwrote the original v1 MP4**. No copy existed elsewhere on the machine
(verified by a bounded search of `%TEMP%`, `%APPDATA%`, `studio/outputs` and `test/`).

Recovery / mitigations actually performed:

1. The improved film was re-rendered with the explicit target `--out preview_v2.mp4`
   (`projects/ww1/render/preview_v2.mp4`) — the Phase 3.1 deliverable was never at risk.
2. The original v1 pixels are preserved here (10 full frames + 5 zoom crops) and inside
   `qa/phase31_diag/before_after.mp4` (the "قبل" side of the three film pairs was extracted from the
   original file before the overwrite), and in `qa/phase31_repro/{before,after}/film/film_*.png`.
3. The v1 **plan** was never modified: `projects/ww1/storyboard/plan.json` still renders today —
   `preview_v1_plan_replay.mp4` is that untouched plan re-rendered with the Phase 3.1 engine, i.e. the
   old layout with the corrected typography (useful as a same-plan comparison, **not** a copy of the
   original defective pixels).
4. The engine now always writes to an explicit path in the Phase 3.1 documentation and commands
   (`rasm.py render … --out …`), and this incident is disclosed in `PHASE3_1_IMPLEMENTATION.md`,
   `PHASE3_1_REVIEWS.md` and `PHASE3_1_IMPLEMENTATION.md`.
