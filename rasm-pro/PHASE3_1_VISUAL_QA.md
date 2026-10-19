# Phase 3.1 — Visual QA Report (artifacts actually reviewed)

Method: every claim below was checked on rendered pixels (MP4 frames, PNM/PNG renders, mosaic sheets),
read as **sequences over time** — not by still-image similarity alone. Timecodes are from the encoded files.
Frames reviewed at full resolution (1280×720) plus zoomed crops for typography.

Artifacts reviewed:

| artifact | what it is |
|---|---|
| `projects/ww1/render/preview_v2.mp4` | **the improved film** (deliverable) — 81.5 s, 1956 frames, 24 fps, 1280×720, AAC 48 kHz SFX-only |
| `projects/ww1/render/preview.mp4` | original v1 film, **lost** on 2026-10-19 (overwritten by a render without `--out`); pixels preserved as stills + in the diagnostic video; plan recoverable as `preview_v1_plan_replay.mp4` (44.54 s, 1069 frames, 24 fps, 1280×720, no audio) |
| `qa/phase31_templates/{premium_whiteboard,documentary_collage,timeline_data_story}.mp4` | 3 cinematic template clips with SFX |
| `qa/phase31_diag/before_after.mp4` | diagnostic comparison video (case headers + 5-step draw sequences + film pairs) |
| `qa/phase31_repro/{before,after}/draw_*_*.png`, `order_*.png` | pre/post per-element draw progressions and segment-order maps |
| `qa/phase31_lab/g{A,B,C,D,F,G,H,I,K}_*.png` | Arabic lab mosaics (K = the film's ten texts verbatim) |

---

## 1. The improved film `preview_v2.mp4` — frame-level review

**Scene 1 — 0:00–0:18 (title + body, `arefruqaa` + `amiri`).** At 0:14.5 the two title lines
«في صيف عام 1914، / اشتعلت الحرب…» sit on the yellow marker band with a hand-drawn double underline;
the digits `1914` are LTR; the body is drawn in dark red in four lines
(«العالمية الأولى بعد اغتيال / الأرشيدوق فرانز فرديناند في سراييفو، / كانت الإمبراطورية الألمانية والنمسا والمجر / في مواجهة…»).
No letter collisions, no chips, no stuck letters; word gaps are clear at full resolution.

**Scene 2 — 0:18–0:35 (collage: two photo cards + caption).** At 0:33 two taped photo cards (tank,
trench) and the hand-written card «معركة السوم» are on screen while the caption
«حفر الجنود الخنادق على الجبهة / الغربية» is being written with the pen visible. Photo reveals are the
intended "torn archive cutout" look (skeleton trace of dark content, fattened brush); the image and its
trace stay aligned (no drift between photo and revealed mask).

**Scene 3 — 0:35–0:49 (three-line display title).** At 0:45 «في عام 1917، دخلت / الولايات المتحدة الحرب /
إلى جانب الحلفاء بعد رسالة زيمرمان» is complete with the double underline; `1917` LTR; the pen leaves
down-right after the last word. The drawing order readable in the sequence is right→left per line, lines
top→bottom, with lifts only between words.

**Scene 4 — 0:49–1:06 (poster card + caption + data line).** At 0:59 the «PEACE SIGNED / Evening Standard»
poster is partly revealed by the mask (torn edges around the headline, inside a paper card), the red card
title «معاهدة فرساي» is finished at top-right, and the caption
«وقّعت ألمانيا معاهدة فرساي / في يونيو 1919، وفرضت عليها / تعويضات ضخمة» is being written
(shadda on «وقّعت» visible). Camera zoom keeps the active line inside the frame.

**Scene 5 — 1:06–1:21.5 (closing).** At 1:18.5 the closing title
«رسمت هذه الحرب خريطة الشرق الأوسط من جديد، وأسست عصبة الأمم» is complete on the marker band with the double
underline, and «هكذا انتهى عصر الإمبراطوريات وبدأ القرن العشرون بوجه جديد» is drawn in red as the final
statement, pen visible on the last word. Clean spacing, correct letterforms, no artifacts at the flourish.

Cross-check: all ten scene texts were independently verified **verbatim** (group K of
`qa/phase31_lab/report.json`: the exact `plan_v2.json` strings with their line breaks, per-element font and
size). Group K results: `cov_struct` 0.9948–1.0, `prec_tol` 0.9857–0.999, `skel_near_ref` 0.999–1.0,
`rtl_start_ok = 1.0`, `teleports = 0` on all ten; mosaic `qa/phase31_lab/gK_filmtexts.png`. (An earlier draft
of this report cited group F as "the film's sentences"; an independent reviewer found group F to be a mix of
script-line strings and truncations — that overstatement is corrected, and group K closes the gap.)

## 2. Defect-by-defect verdict (user's report)

| user's wording | verdict | evidence |
|---|---|---|
| حروف متلاصقة / عالقة (crowded, stuck letters) | fixed | subpath pieces per element 1338→56, 1410→178, 225→32, 1614→73; lab `cov_struct` min 0.974; film frames above show separated letterforms at full resolution |
| وقفات ورفعات قلم غير طبيعية (unnatural pen pauses/lifts) | fixed | word-union tracing ⇒ lifts only at real gaps/dots; `teleports = 0` in all 145 lab cases and in the film elements; J group: 14 downs / 14 ups balanced, state machine ordered |
| بدايات خاطئة (wrong start positions) | fixed | RTL runs emitted right→left (`glyph_iter = list(reversed(gs))`); `rtl_start_ok = 1.0` on 104 word/letter cases; order maps show the first (red) segments on the right; digits start left (LTR) |
| أشكال حروف غير دقيقة (inaccurate letterforms) | fixed | Guo–Hall thinning (single connected skeleton), word masks traced as one unit; lab `prec_tol` min 0.9491, `skel_near_ref` 1.0; diacritics tested (6 cases) |
| مظهر «مولّد تقنيًا» (technically generated look) | improved | 3 cinematic templates + real SFX + hand-drawn decorations (marker band, double underline, flourish, cards, tape); pen sprite follows stroke direction with smoothed rotation; before/after video shows the change |

## 3. Template clips

| clip | duration | reviewed | verdict |
|---|---|---|---|
| `premium_whiteboard.mp4` | 28.5 s (684 f) | full clip + frames 24.5/27/28.2 s | title/body/card composition; at 28.2 s the hand-drawn dark-red **arrow** lands on the photo card (element `arrow_at_end` verified); wavy card edges and tape visible; SFX present |
| `documentary_collage.mp4` | 29.29 s (703 f) | full clip + frames 16/22.5/28.5 s | taped photo cards, torn paper strips, red underline; camera settles on the closing strip «قصاصات ورقية وأشرطة لاصقة وظلال ناعمة» (28.5 s) — Arabic clean, RTL correct |
| `timeline_data_story.mp4` | 26.58 s (638 f) | full clip + frames 21 s + zoom crop | axis + 3 bars with values 40/65/85 and years 1914/1916/1918; **labels at natural size** (the Phase-3.1 label-upscaling defect is gone — zoom crop shows crisp glyphs); sub-labels enlarged to 0.62× label size (legibility pass); demo title is explicitly «قالب بيانات (عرض توضيحي)» |

All three are integrated into the planner (`director.py` element types + `engine/render/templates.py`) and
are Arabic-capable (they were produced with Arabic labels). Demo numbers are labelled as a demo
(`عرض توضيحي`) — they are not presented as real statistics.

## 4. Diagnostic video `qa/phase31_diag/before_after.mp4` (36.7 s, 880 frames)

Intro → for each of the 4 measured elements a numbers card (pieces/strokes/teleports before→after) → five
draw-progress frames 20/45/70/90/100 % before|after side by side → 3 film pairs (v1 vs v2 at the title,
the image card, the ending) → summary card. All Arabic labels in this video are drawn **by the engine
itself** (`text_to_strokes` + `Whiteboard.paint`), which is also an implicit sanity test: any regression in
shaping/spacing would be visible in the video's own captions.

Standalone stills kept: `qa/phase31_repro/{before,after}/draw_*.png` (40 frames) and the extracted film
pairs; `qa/phase31_repro/{before,after}/film/film_*.png`.

## 5. Residual visual limitations (disclosed, accepted)

1. **Camera vs large elements**: while the camera zooms/pans between elements, a large card can be
   momentarily cropped at the frame edge (seen in `documentary_collage.mp4` around 0:16, and in scene 2 of
   the film). The active element stays visible and the camera settles; treated as an accepted cinematic
   trade-off, not a defect.
2. **Image reveals are skeleton traces** (dark content + fattened brush): a deliberate "torn cutout" look.
   Thin, low-contrast details may not be traced; the poster and tank cards were checked to be legible.
3. **Pen sprite is a generic marker**, rotated around its tip and smoothed (18 % per frame); it is not a
   photographic hand/pen asset. Contact is verified numerically (J group, ≤ 0.47 px through real camera
   transforms).
4. **Within-glyph stroke order is geometric** (right-most terminal, direction-continuity walk). It looks
   natural at 24 fps but is not calligraphic order — see `PHASE3_1_ROOT_CAUSE.md`, RC2 limitations.
5. The v1 film remains the reference of the "before" state; the two films differ in pacing too
   (v2 = natural pacing × 0.72, disclosed in `PHASE3_1_IMPLEMENTATION.md`), so a frame-perfect side-by-side
   is not possible — the pairs in the diagnostic video were chosen at matching *content* moments.

## 6. Reviews

Independent, role-based reviews of the actual artifacts were performed by fresh automated reviewers
(disclosed: these are agent reviews, not human reviewers); their findings and dispositions are recorded in
`PHASE3_1_REVIEWS.md`. Verified summaries in §1–§3 above are the author's own frame-level checks.
