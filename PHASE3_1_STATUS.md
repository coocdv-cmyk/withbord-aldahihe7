PHASE_3_1_STATUS = PASS_WITH_LIMITATIONS

Reason: all acceptance criteria were met with hard evidence on the current code state:

  - Arabic visual regression lab: 145/145 cases pass (104 letter/word cases, 10 film texts verbatim,
    4 mixed-direction, 1 long text, 10 sentences, 16 pen/contact checks), teleports = 0,
    fallback_tokens = 0, cov_struct min 0.974 (mean 0.9949), prec_tol min 0.9491, skel_near_ref
    min 0.999, rtl_start_ok = 1.0 on all RTL strokes, digits_ltr_first_stroke_left = true.
  - Unit tests: 24/24 pass, including 5 new tracer-equivalence tests + bit-identical re-trace of the
    three real ww1 images (819 / 14 / 140 strokes, 39 732 points).
  - Three root causes fixed (Zhang-Suen fragmentation, HarfBuzz RTL emission order, paint() pen-lift
    concatenation) with hard before/after numbers (pieces 1338→56, 1410→178, 225→32, 1614→73;
    teleports 2→0). Plus five integration defects (SFX mux, ImageReveal alignment, reveal duration,
    label upscaling, validate_video expect_audio).
  - Performance: raster trace 111.4 s → 7.39 s (15.1×) with bit-identical output; cold scene prep
    650.4 s → 48.5 s (13.4×); cache hit rate 1.0 warm.
  - Improved film rendered and FFprobe-validated: projects/ww1/render/preview_v2.mp4, 1956 frames,
    81.5 s, 24 fps, 1280×720, h264, AAC 48 kHz mono, A/V delta 0.007 s, SFX only (no narration).
  - Three cinematic template clips rendered and FFprobe-validated (premium_whiteboard 28.5 s,
    documentary_collage 29.29 s, timeline_data_story 26.58 s).
  - Before/after evidence: qa/phase31_repro/{before,after} (draw/order PNGs), qa/phase31_diag/before_after.mp4
    (36.67 s, 880 frames), qa/phase31_ffprobe.txt.
  - Deliverables: PHASE3_1_ROOT_CAUSE.md, PHASE3_1_ARABIC_TESTS.md, PHASE3_1_PERFORMANCE.md,
    PHASE3_1_VISUAL_QA.md, PHASE3_1_IMPLEMENTATION.md, PHASE3_1_REVIEWS.md.
  - Independent reviews: Arabic (1 medium finding, fixed via group K), film (no critical/major defects;
    1 minor legibility item fixed, rest disclosed), engineering (no implementation defect found; 19 stale
    documentation statements, all corrected in this pass).

Limitations (disclosed, not defects):

  1. Incident: the original v1 baseline MP4 (projects/ww1/render/preview.mp4) was overwritten on
     2026-10-19 by a render command that omitted --out. Its pixels are preserved as stills
     (qa/phase31_repro/before/film/ and qa/phase31_repro/before/film_v1_stills/) and inside
     qa/phase31_diag/before_after.mp4; the v1 plan re-renders as
     projects/ww1/render/preview_v1_plan_replay.mp4. The original MP4 file itself no longer exists.
  2. Within-glyph stroke order is geometric (right-most terminal + direction continuity), not
     calligraphic; closed-loop initial forms (e.g. the head of م) cannot start at their extreme right
     pixel (rtl_start_ok 0.941 on the longest sentence).
  3. Audio content (SFX only, no narration) was not ear-verified; verified structurally (event stream
     1 093 down / 1 093 up / 27 taps / 4 slides, AAC mono 48 kHz, A/V delta 0.007 s).
  4. Paper-slide SFX are procedurally generated (no free recording available); pen sounds are real PD
     recordings (PDSounds #179/#180 by stephan, 2007).
  5. Timeline sub-labels are the smallest text in the film (enlarged 0.52 → 0.62 in this pass but still
     small at 1280×720).
  6. Performance "before" figures (111.4 s, 650.4 s, 118.9 s) are single historical measurements and
     cannot be reproduced from saved artifacts; the optimisation itself is proven output-identical by
     tests/test_mask_path_equiv.py and tools/verify_raster_equiv.py.