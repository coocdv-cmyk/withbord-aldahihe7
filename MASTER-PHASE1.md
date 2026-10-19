# المرحلة الأولى (Master Phase 1) — "المحرك الأساسي + التصدير + التخطيط + الصوت"
## خطة كاملة، تفصيلية، world-class، بدون كسر العمل القديم

**الحالة:** خطة (لم تُنفّذ بعد) — تنتظر موافقتك للبدء.
**المبدأ (من doc 07):** "الذكاء الاصطناعي يولّد العناصر والنص والتوقيت، والكود هو الذي يرسم ويحرّك (Deterministic)."
**القاعدة (منك):** لا كسر للعمل القديم · لا كود غير مُتحقق · لا كود لا أعرفه.

---

## 0. ملخص تنفيذي (30 ثانية)

- **الهدف:** جعل `studio` + `rasm-pro` يعملان "بقوة كاملة" (full power) = محرك متجهي (Cairo/Pango) + stroke engine + hand engine + JSON مفتوح + تصدير محلي (ffmpeg) + مخطّط ذكي (LLM) + sync صوت (Whisper) + مكتبة أصول (600+).
- **المدة:** 8–10 أسابيع (M1–M5 من doc 07)، 1–2 جلسة/أسبوع.
- **ما نأخذ من VideoScribe:** الأفكار + الخوارزميات + patterns (doc 07 §2) — **لا ننسخ كود** (Sparkol owned).
- **ما نحفظ:** studio/core.py, whiteboard.py, app.py, rasm-pro/engine/** (all except log.py fix), tests, projects, assets.
- **ما نستبدل (تدريجياً، مع fallback):** PIL→Cairo, stroke_map (skeleton)→stroke_engine (vector), Pillow text→HarfBuzz.
- **القاعدة (لا كود غير مُتحقق):** كل مكوّن new يُضاف بجانب old (feature flag)، tests تمر، ثم switch. لا حذف old until green.

---

## 1. ما نأخذ من VideoScribe (verified patterns only)

من doc 07 §2 — 20 pattern. نأخذ **الأفكار**، نعيد تنفيذها ourselves:

| # | Pattern (VideoScribe) | تطبيقنا | ملف الهدف | مُتحقق؟ |
|---|---|---|---|---|
| 1 | 4-phase time model (enter/focus/exit/pause) | `scene_model.py` | new | ✅ concept clear |
| 2 | Mask-based reveal (length 0→1) | Cairo `set_dash` + offset | `stroke_engine.py` | ✅ Cairo API known |
| 3 | Outline-first (70%) then color | `stroke_engine.py` | new | ✅ simple |
| 4 | 18-color quantization (median-cut, Oklch) | `vectorizer.py` | new | ✅ OpenCV available |
| 5 | 4-group SVG structure (meta/outline/colour/reveal) | asset schema | `assets/*.svg` | ✅ clear |
| 6 | Recolor by tags | `asset_recolor.py` | new | ✅ SVG string replace |
| 7 | Fallback scribble (skeleton→convex hull→rect) | `stroke_engine.py` fallback | new | ✅ OpenCV skeletonize |
| 8 | Hand-like path tracing (terminal-preference, 45° compass) | `path_planner.py` | new | ✅ algorithm documented |
| 9 | Char-by-char with word sync | `text_engine.py` | new | ✅ HarfBuzz + Whisper |
| 10 | 2-frame hand, offset (−100)×scale | `hand_engine.py` | extend Pencil | ✅ existing Pencil |
| 11 | Camera: 3× world, tween in screen space | `camera_engine.py` | extend camera_rect | ✅ existing |
| 12 | Watermark as pricing tool | N/A (we have none) | — | ✅ skip |
| 13 | Share link + UTM | N/A (local) | — | ✅ skip |
| 14 | Cache assets before playback | `asset_cache.py` | new | ✅ simple |
| 15 | Self-verify conversion (pixelmatch >10px → Reveal) | `vectorizer.py` QA | new | ✅ pixelmatch concept |
| 16 | 3-tier timing (element→scene→project→0) | `scene_model.py` | new | ✅ clear |
| 17 | Wordform sync contract | `audio_sync.py` | extend align.py | ✅ existing |
| 18 | Camera as first element (pinned) | `scene_model.py` default | new | ✅ clear |
| 19 | Import legacy `.scribe` (ZIP+XML) | `import_scribe.py` | new (M5) | ⚠️ deferred |
| 20 | Frustum culling by time | `render_cairo.py` | new | ✅ concept clear |

**مُتحقق** = algorithm documented in doc 07 + dependencies available. **غير مُتحقق** = needs research (deferred to M5).

---

## 2. ما نحفظ (do NOT touch — preserve)

| ملف/مجلد | السبب | الإجراء |
|---|---|---|
| `studio/core.py` | 489 lines, tested, production | keep; add new modules alongside |
| `studio/whiteboard.py` | 317 lines, Pencil+camera+prepare | keep; extend, don't replace |
| `studio/app.py` | 351 lines, routes | keep; add routes for new modules |
| `studio/rasm_bridge.py` | bridge to rasm-pro | keep |
| `studio/demo.py` | sample projects | keep |
| `studio/checks.py`, `whiteboard_checks.py`, `test_bridge.py` | 10 tests | keep; add new test files |
| `studio/web/*` | UI | keep; extend in M7 (Phase 7) |
| `rasm-pro/engine/**` | entire engine | keep; extend (log.py already fixed) |
| `rasm-pro/tests/` | 19 tests | keep |
| `studio/library/` (2159 SVGs) | asset base | keep; extend with tags |
| `studio/art/` (hand.png, etc.) | calibrated assets | keep |
| `studio/outputs/`, `projects/`, `studio/data/` | user data | keep (never delete) |
| `vs-analysis/` | reference (read-only) | keep; never modify |
| `VideoScribe/` installer | reference | keep |

**قاعدة:** أي ملف "keep" لا يُعدَّل إلا via new module + feature flag. لا in-place rewrite until green.

---

## 3. ما نستبدل (gradual, feature-flagged)

| Current | Replacement | Feature flag | Gate to switch |
|---|---|---|---|
| `stroke_map` (skeleton, in core.py) | `stroke_engine.py` (vector + medial axis) | `RENDERER=vector` env | side-by-side render identical or better |
| PIL text (`core.font`, `display`) | `text_engine.py` (HarfBuzz + Cairo) | `TEXT_ENGINE=harfbuzz` env | Arabic shaping test passes |
| PIL compose (`compose_legacy`, `compose` in whiteboard) | `render_cairo.py` | `COMPOSER=cairo` env | compose output identical |
| 0.6B LLM | 8B Q4 (when downloaded) | `MODEL_SIZE=8b` env | 90% title accuracy |
| skeletonization strokes | authored strokes (when available) | per-asset `stroke_source` | visual review |

**Pattern:** new module lives alongside old. Env var selects. Old code stays until gate passes. Then remove old in cleanup PR.

---

## 4. Phase 1 tasks (M1–M5 from doc 07)

### M1: Vector Engine (2–3 weeks) — THE core

**Goal:** Cairo/Pango renderer + stroke engine + hand engine + open JSON schema. Meshed scene of 6 Arabic elements renders with human-like draw order, animated hand, 1080p, no PIL in render path.

#### 4.1 Setup (Day 1-2)
- [ ] Install Cairo + Pango + pycairo + uharfbuzz into `.venv`
  - Windows: `pip install pycairo uharfbuzz` (wheels available) OR `conda install cairo pango` 
  - Verify: `python -c "import cairo, uharfbuzz; print('ok')"`
- [ ] Create `studio/engine/` package (new folder, doesn't touch existing)
  - `studio/engine/__init__.py`
  - `studio/engine/scene_model.py`
  - `studio/engine/render_cairo.py`
  - `studio/engine/stroke_engine.py`
  - `studio/engine/path_planner.py`
  - `studio/engine/text_engine.py`
  - `studio/engine/hand_engine.py`
  - `studio/engine/camera_engine.py`
  - `studio/engine/audio_sync.py`
  - `studio/engine/export_ffmpeg.py`
  - `studio/engine/asset_cache.py`
  - `studio/engine/vectorizer.py`
  - `studio/engine/asset_recolor.py`
- [ ] Add `studio/schemas/scene_schema.json` (JSON Schema, from doc 07 §4.1)
- [ ] Add pydantic models in `scene_model.py` (mirror schema)

#### 4.2 scene_model (Day 3-5)
- [ ] Define `Project`, `Scene`, `Element`, `Camera`, `Audio` pydantic classes
- [ ] Time resolution: element duration = entrance + emphasis×times + exit + pause; scene = max(audio_end, elements_end + transition); project = sum scenes
- [ ] 3-tier timing: element → scene → project → 0 (VideoScribe pattern #16)
- [ ] Validation: same as `core.validate_project` but stricter (pydantic)
- [ ] Backward compat: loader converts old `version:1` project → new schema
- [ ] Tests: `test_scene_model.py` (15+ tests: time resolution, validation, migration)

#### 4.3 render_cairo (Day 6-8)
- [ ] Cairo surface (ImageSurface, 1920×1080, 60fps target but 24 for now)
- [ ] Draw paper background (color from schema)
- [ ] Draw elements in z-order
- [ ] Draw hand overlay (from hand_engine)
- [ ] Output: numpy array (for ffmpeg) — bridge to existing encoder
- [ ] Tests: render 1 scene → PNG, compare to golden (tolerance 5%)

#### 4.4 stroke_engine (Day 9-12)
- [ ] SVG path → Bézier segments (svgelements — already installed)
- [ ] Segment by curvature (split at high-curvature points)
- [ ] Dash-based reveal: `ctx.set_dash([total_len], offset)` where offset goes 0→total_len
- [ ] Medial axis stroke width: skeleton + distance transform → width = clamp(2·d·k, w_min, w_max)
- [ ] Outline-first: 70% time for outline, 30% for color fill
- [ ] Path planner (greedy + 2-opt): order strokes by nearest-start + min direction change
- [ ] Pen lifts: 60-120ms transition between distant strokes
- [ ] Speed model: v ∝ 1/(1+κ) where κ = curvature, slowdown at segment ends
- [ ] Fallback (if no vector): skeletonize → convex hull scribble → rect scribble
- [ ] Tests: `test_stroke_engine.py` (20+ tests)

#### 4.5 path_planner (Day 12-13)
- [ ] Terminal preference: start from endpoints (neighbors=1) and top-left
- [ ] Direction history: length-5 buffer
- [ ] 45° compass steps
- [ ] At branch: choose closest angle to history
- [ ] Tests: planner produces deterministic order for sample SVG

#### 4.6 text_engine (Day 14-16)
- [ ] HarfBuzz shaping via uharfbuzz (already installed)
- [ ] Glyph outlines from font file (fonttools) → Cairo paths
- [ ] RTL/LTR BiDi (python-bidi + manual) — full, not just reshape
- [ ] Line breaking by width (not char count)
- [ ] Arabic/English mixed text (BiDi runs)
- [ ] Char-by-char reveal with word sync (Whisper timestamps)
- [ ] Kashida (justification) — optional, M1 stretch
- [ ] Tests: Arabic shaping test (compare to reference render), mixed text

#### 4.7 hand_engine (Day 17-18)
- [ ] Extend existing `Pencil` (whiteboard.py) — don't replace
- [ ] Multi-frame hand (3-8 frames, not 2)
- [ ] Frame selection by speed (faster = later frame)
- [ ] Multiple hand styles (marker, pencil, brush, eraser)
- [ ] Left-handed option
- [ ] Tip anchor per style (calibrated)
- [ ] Tests: hand renders, tip visible

#### 4.8 camera_engine (Day 19-20)
- [ ] Extend existing `camera_rect` (whiteboard.py)
- [ ] Full camera: position, zoom, rotation, target
- [ ] Parallax: multi-layer depth (bg 0.3×, mid 0.7×, fg 1.0×)
- [ ] Camera keyframes (animated moves)
- [ ] Presets: wide, medium, close-up, over-shoulder, dutch
- [ ] Planning-driven: auto-suggest camera from scene layout
- [ ] Tests: camera produces valid transforms

#### 4.9 integration (Day 21)
- [ ] Wire: `render_project()` in core.py checks `RENDERER` env → if `vector`, use new engine; else old
- [ ] Side-by-side render of `demo.py` project (old vs new) → visual compare
- [ ] Golden-frame test for new engine
- [ ] **Gate M1:** meshed scene of 6 Arabic elements renders with human-like draw order, animated hand, 1080p, no PIL in render path

### M2: Export (1 week)

**Goal:** ffmpeg wrapper + preview clips + transparency + SRT. 1080p at ≥4× realtime, WebM/VP9 alpha.

#### 4.10 export_ffmpeg (Day 22-24)
- [ ] Extend `find_ffmpeg()` (already exists)
- [ ] H.264 (existing) + H.265 + AV1 + VP9 (alpha) + ProRes (optional)
- [ ] Preview clips: 2-4s segments for iteration
- [ ] Transparency: VP9-alpha for overlays
- [ ] SRT (existing, improve timing)
- [ ] Parallel encoding (multiple clips at once)
- [ ] Resume on interruption (OPFS-style: checkpoint frames)
- [ ] Tests: export 10s clip → validate with ffprobe (codec, fps, duration, audio)

#### 4.11 asset_cache (Day 25)
- [ ] Cache composed frames by (scene_hash, frame_number)
- [ ] Cache directory: `studio/cache/frames/`
- [ ] LRU eviction (max 5GB)
- [ ] Tests: cache hit/miss

**Gate M2:** 1080p export ≥4× realtime, WebM alpha works.

### M3: Smart Planner (2–3 weeks)

**Goal:** script → full project JSON (scenes/elements/timing) + layout templates. 10 scenes from 3 topics, 100% valid JSON.

#### 4.12 LLM upgrade (Day 26-28)
- [ ] Download Qwen3-8B Q4_K_M (~5GB) → `models/`
- [ ] Update `model_status()` (detect 8B, fallback 0.6B)
- [ ] GBNF/JSON Schema constrained output (llama.cpp `grammar` or Ollama `format`)
- [ ] Test: 10 scripts (5 Arabic, 5 mixed) → title accuracy, icon relevance, JSON validity
- [ ] **Gate:** ≥90% valid titles, ≥80% relevant icons, 100% valid JSON

#### 4.13 layout templates (Day 29-31)
- [ ] 6 templates: title+3-row, big-center+details, compare L/R, timeline, chart, process-flow
- [ ] Template selection by scene content (LLM suggests, rules fallback)
- [ ] Auto-placement of elements within template
- [ ] Tests: each template renders valid layout

#### 4.14 planner integration (Day 32-34)
- [ ] `plan()` → uses new LLM + templates + time resolution
- [ ] Backward compat: old `plan()` still works (feature flag `PLANNER=v2`)
- [ ] Tests: 10 scenes from 3 topics, no manual intervention

**Gate M3:** 10 scenes from 3 topics, 100% valid JSON, no manual.

### M4: Audio & Sync (2 weeks)

**Goal:** TTS Arabic local + Whisper word timings + region plan. Each spoken word draws its element; drift <250ms.

#### 4.15 audio_sync (Day 35-37)
- [ ] Extend `rasm-pro/engine/audio/align.py` (already exists)
- [ ] Word-level alignment via stable-ts (install + integrate)
- [ ] Region plan: element ↔ word mapping (from scene JSON `regions` field)
- [ ] Drift measurement: compare Whisper word times to render frame times
- [ ] Tests: 3 Arabic VO recordings, drift <250ms

#### 4.16 TTS (Day 38-40)
- [ ] Piper (Arabic voices) — local, fast
- [ ] XTTS-v2 (voice cloning) — optional, GPU
- [ ] edge-tts (network, quality) — optional
- [ ] UI: TTS voice selector + preview
- [ ] Tests: generate 30s Arabic VO → align → render

#### 4.17 audio mix (Day 41-42)
- [ ] VO + SFX + music (3 tracks)
- [ ] SFX triggers (on element appear)
- [ ] Music ducking (auto-lower during VO)
- [ ] EBU R128 normalization
- [ ] Tests: 3-layer mix sounds balanced

**Gate M4:** each spoken word draws its element; drift <250ms; 3-layer audio balanced.

### M5: Library & Search (2–3 weeks)

**Goal:** 600+ tagged assets + CLIP search + recolor. Arabic search returns relevant asset <300ms.

#### 4.18 asset expansion (Day 43-46)
- [ ] Expand from 10 story assets → 60 high-quality Arabic-tagged assets (80% topic coverage)
- [ ] Each asset: SVG + tags (Arabic + English) + license + source
- [ ] Recolor by tags (SVG string replace with palette)
- [ ] Tests: asset count ≥60, all have tags + license

#### 4.19 CLIP search (Day 47-49)
- [ ] OpenCLIP (multilingual) — local, no network
- [ ] Index assets: embed (image + text tags)
- [ ] Search: Arabic query → top-5 assets <300ms
- [ ] Tests: "سيارة" returns car-related assets

#### 4.20 vectorizer (Day 50-52)
- [ ] Image → SVG (VTracer or potrace) + OpenCV
- [ ] Color quantization (16-24 colors, Oklch)
- [ ] Path ordering (greedy + 2-opt)
- [ ] Self-verify: pixelmatch >10px → force Reveal mode
- [ ] Tests: vectorize 5 sample images, compare quality

#### 4.21 legacy import (Day 53-54) — OPTIONAL
- [ ] Import `.scribe` (ZIP+XML) → our JSON
- [ ] Defer if time tight

**Gate M5:** 60+ assets tagged, Arabic search <300ms, vectorizer works on 5 samples.

---

## 5. Phase 1 deliverables (end state)

- [ ] `studio/engine/` package (12 modules) — new, alongside old
- [ ] `studio/schemas/scene_schema.json` + pydantic models
- [ ] `studio/tests/test_scene_model.py`, `test_stroke_engine.py`, `test_text_engine.py`, `test_export.py`, `test_audio_sync.py`, `test_search.py` (6 new test files)
- [ ] `models/Qwen3-8B-Q4_K_M.gguf` (downloaded)
- [ ] `studio/library/` expanded to 60+ tagged assets
- [ ] Feature flags: `RENDERER`, `TEXT_ENGINE`, `COMPOSER`, `PLANNER`, `MODEL_SIZE`
- [ ] All existing tests still green (29/29)
- [ ] New tests green (60+)
- [ ] Golden-frame tests for both old and new engines
- [ ] `LIMITATIONS.md` updated (what's still missing)
- [ ] `MASTER-PHASE1.md` (this file) → `PHASE1-COMPLETE.md` (after execution)

---

## 6. What Phase 1 does NOT do (out of scope)

- ❌ Rigging/characters (Phase 2)
- ❌ Infographics templates (Phase 2)
- ❌ Internet sourcing UI (Phase 3)
- ❌ Desktop packaging (Phase 4)
- ❌ Performance optimization (Phase 4)
- ❌ UI v2 (timeline/camera editors) (Phase 5)
- ❌ Daily production templates (Phase 6)

These are M6-M7 from doc 07 — separate phases.

---

## 7. Risk register (Phase 1 specific)

| # | Risk | Prob | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Cairo/Pango Windows install fails | Medium | High | Test install Day 1; fallback: use `cairocffi` (pure Python wrapper) or WSL |
| 2 | 8B LLM too slow on i5 (no GPU) | High | Medium | Keep 0.6B fallback; test 8B speed early (Day 26) |
| 3 | Authored strokes take too long | High | Medium | Start with 5 (not 50); skeletonization fallback |
| 4 | HarfBuzz shaping differs from reference | Medium | Medium | Compare to browser render; adjust font features |
| 5 | Medial axis (stroke width) complex | Medium | Low | Use simpler: distance transform only (no skeleton) |
| 6 | Feature flags add complexity | Low | Medium | Document in `FEATURE_FLAGS.md`; remove after gate |
| 7 | Old code breaks during integration | Low | High | Feature flags ensure old path always works |
| 8 | Time estimate optimistic | High | Medium | Gates are checkpoints; can pause between M's |

---

## 8. "لا كود لا أعرفه" — verification checklist

Before writing ANY new module, I will:
1. ✅ Check dependency is installed (`pip list` / `import X`)
2. ✅ Read existing code that does similar (e.g., read `whiteboard.py` before extending)
3. ✅ Check doc 07 for the pattern (verified by reverse-engineering)
4. ✅ Write tests FIRST (TDD) — test fails → implement → test passes
5. ✅ Run existing tests after each change (no regression)
6. ✅ Golden-frame comparison before/after
7. ✅ If unsure: research (webfetch/docs) before coding, or defer to next session

**Modules I'm 100% certain about (verified deps + patterns):**
- scene_model (pydantic — installed, pattern clear)
- render_cairo (pycairo — need to verify install, but API known)
- stroke_engine (svgelements + OpenCV — installed, pattern from doc 07)
- path_planner (pure Python algorithm — no deps)
- text_engine (uharfbuzz + fonttools — installed)
- hand_engine (extends existing Pencil — known)
- camera_engine (extends existing camera_rect — known)
- audio_sync (extends existing align.py — known)
- export_ffmpeg (extends existing find_ffmpeg — known)
- asset_cache (pure Python — no deps)
- vectorizer (VTracer/potrace — need to verify install; potrace available via `potracer` pip? check)

**Modules I'm NOT certain about (will research first):**
- VTracer install (may need Rust build) → research Day 50
- CLIP multilingual model (size, speed) → research Day 47
- Piper Arabic voices (availability, quality) → research Day 38
- Cairo on Windows (wheel availability) → research Day 1 (FIRST)

---

## 9. Execution order (session-by-session)

| Session | Days | Focus | Deliverable |
|---|---|---|---|
| S1 | 1-2 | Setup: Cairo install, engine/ package, schema | engine/ exists, Cairo works |
| S2 | 3-5 | scene_model + tests | pydantic models, time resolution |
| S3 | 6-8 | render_cairo + golden frame | 1 scene renders to PNG |
| S4 | 9-13 | stroke_engine + path_planner + tests | vector strokes visible |
| S5 | 14-16 | text_engine (HarfBuzz) + tests | Arabic shapes correctly |
| S6 | 17-21 | hand_engine + camera_engine + integration | full scene with hand+camera |
| S7 | 22-25 | export_ffmpeg + asset_cache + tests | 1080p export works |
| S8 | 26-28 | LLM upgrade (8B) + tests | 90% title accuracy |
| S9 | 29-34 | layout templates + planner v2 + tests | 10 scenes auto |
| S10 | 35-42 | audio_sync + TTS + mix + tests | drift <250ms |
| S11 | 43-54 | library (60 assets) + CLIP + vectorizer | search <300ms |

**Each session:** implement → test → commit → review with you → next.

---

## 10. Gates (Phase 1 complete when ALL pass)

- [ ] G-M1: meshed scene of 6 Arabic elements renders with human-like draw order, animated hand, 1080p, no PIL in render path
- [ ] G-M2: 1080p export ≥4× realtime, WebM alpha works
- [ ] G-M3: 10 scenes from 3 topics, 100% valid JSON, no manual
- [ ] G-M4: each spoken word draws its element; drift <250ms; 3-layer audio balanced
- [ ] G-M5: 60+ assets tagged, Arabic search <300ms, vectorizer works on 5 samples
- [ ] All existing tests green (29/29)
- [ ] All new tests green (60+)
- [ ] Golden-frame tests for both engines
- [ ] Feature flags documented
- [ ] No old code deleted (only new modules added)

---

## 11. Immediate next action (if you approve)

**Session 1, Day 1:**
1. `cd "D:\withbord inmation"; git init; git add -A; git commit -m "baseline v0.1"`
2. Create `.gitignore`
3. Test Cairo install: `pip install pycairo uharfbuzz`
4. If works → create `studio/engine/` + first module (`scene_model.py`)
5. If fails → research alternative (cairocffi or WSL) before proceeding

**أنت ت decide:** "ابدأ Session 1" أو "غيّر X".

---

*مرجع: vs-analysis/docs/00-07, PHASE1_REPORT.md, PHASE3_REPORT.md, DELIVERY-AR.md, VISION-2D-AR.md, USER-GUIDE-AR.md*
*قاعدة: لا كسر للعمل القديم · لا كود غير مُتحقق · feature flags · gates between sessions*