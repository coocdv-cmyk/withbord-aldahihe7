# Rasm Pro: engineering and product handover

**Reviewed:** 20 October 2026.  
**Primary engine:** `D:\withbord inmation\rasm-pro`.  
**Repository root:** `D:\withbord inmation`.  
**HEAD inspected:** `ed66355`, preceded by `e6f77d5` and `494cea3`.  
**Scope:** source inspection and previously saved evidence. No tests, model inference, network research, asset generation, or video rendering were executed to produce this document. This is not a release certification.

## 1. Product intent and current maturity

Rasm Pro is a local Python engine for explanatory videos using whiteboard drawing, ink, paper, documentary collage, image reveals, a pen overlay, and camera movement. It renders a structured scene plan. It is not a neural text-to-video generator.

The owner wants an independent application: enter a script, optional sources and narration, review unresolved decisions, preview, and export without editing code or relying on a coding assistant. English production is the priority; Arabic support must remain intact.

The eventual operational target is 20–30-minute episodes and three publications per week. This throughput has not been established by measured end-to-end production on the laptop. Shorter episodes, imported narration, limited templates, and reviewed assets are the proposed first release—not a proven hardware ceiling.

Existing capabilities include a functioning renderer, a short Arabic reference film, text shaping and stroke extraction, templates, asset generation, source adapters, narration import, sound effects, and a local UI bridge. Research verification, production integration, long-video recovery, and standalone distribution remain incomplete.

## 2. Non-negotiable project decisions

- Keep rasm-pro as the primary implementation. Studio may provide a UI and external runtimes; do not develop a competing research engine there.
- Preserve the existing style, projects, reference outputs, Arabic fixes, and English corrections.
- Prefer incremental changes over a wholesale rewrite.
- Keep rendering independent of the language model and Torch.
- Qwen is an assistant, not a final fact, identity, or permissions authority.
- Generated artwork is illustration, not historical evidence.
- Do not silently switch to paid/cloud inference, download models, or retrain.
- Human review remains necessary for ambiguous assets, important factual claims, pronunciation, and final approval.
- Animated presenters, CPU training, and 4K/60fps are outside the initial release.

## 3. Hardware and execution environment

Previously read hardware: Intel i5-1135G7, four cores/eight logical processors, approximately 16GB RAM, Intel Iris Xe graphics. Do not assume a discrete GPU or CUDA.

Use sequential heavy jobs, bounded network concurrency, caches, low-resolution previews, and selective rerendering. Avoid concurrently running Qwen, SD1.5, and final rendering by default. Benchmark thread counts rather than assuming eight logical processors support eight heavy jobs.

There are separate Python environments:

- `rasm-pro/.venv`: primary engine.
- Repository `.venv`: Studio launcher/UI environment.
- Repository `.venv-gen`: Torch/Diffusers image-generation worker.

An installed dependency in one environment is not necessarily available in another. The primary requirements file currently lists packages without version pins.

## 4. Source map

| Path relative to rasm-pro | Responsibility |
|---|---|
| `rasm.py` | CLI orchestration |
| `engine/core` | Paths, configuration, utilities, rational timebase, logging |
| `engine/providers/llm.py` | Older general-purpose language client |
| `engine/stages/understanding.py` | Script graph, heuristic extraction, optional scene enrichment |
| `engine/stages/research.py` | Older research orchestration used by the current planner |
| `engine/stages/plan.py` | Basic storyboard and element construction |
| `engine/stages/validate_plan.py` | Structural plan validation |
| `engine/research` | Adapters, HTTP/store/rights, newer evidence workflow |
| `engine/assets` | Procedural/SD asset studio, processing, QA, approval metadata |
| `engine/strokes` | Text/SVG/raster geometry and pen timing |
| `engine/render` | Canvas, templates, camera, director, FFmpeg writer, media checks |
| `engine/audio` | Narration import/probe, approximate alignment, SFX and mixing |
| `engine/memory` | Persistent alias/type/need corrections, not model training |
| `assets/fonts`, `assets/sfx` | Fonts and writing recordings |
| `assets/generated` | Generated assets, manifests, approval records; Git-ignored |
| `style_packs/paper_ink_v1.json` | Locked appearance and asset QA configuration |
| `library`, `cache`, `projects`, `logs` | Local assets, caches, production data, logs |
| `tests`, `tools`, `qa`, `docs` | Regression tests, diagnostics, evidence, documentation |

Repository-level `studio/rasm_bridge.py` connects the UI to the engine. `studio/runtime` and `studio/models` contain external runtime/model dependencies. `gen` contains shared image-processing helpers. `local-model-audit` and `engine-review-20261019` contain historical evaluation evidence. Reverse-engineering/reference folders are not the production engine.

## 5. Actual pipelines

### Existing production-oriented path

```text
script
  -> understand
  -> script/scriptgraph.json
  -> older research stage
  -> research/research.json + assets.json + CREDITS.md + assets/
  -> plan
  -> storyboard/plan.json
  -> plan validation
  -> text/SVG/raster geometry
  -> Director + canvas + camera + pen
  -> FFmpeg video
  -> CLI SFX construction/mux + FFprobe validation
```

### New evidence path

```text
script/SRT + optional URLs/documents
  -> ResearchWorkflow
  -> requirements, sources, candidates, evidence, budgets, resumable state
  -> evidence.json + evidence_state.json + evidence_summary.json
  -> automatic production-plan integration is incomplete
```

The planner and automatic render fallback still read the older `research.json`. Running `evidence` does not automatically make its reviewed selections drive the existing planner.

The documented project skeleton includes `renders/`, but existing production commands/projects also use `render/`. Inspect consumers before normalizing paths.

## 6. Data contracts

**ScriptGraph:** language, scenes, narration, duration, entities, needs, claims, timeline, statistics, source hash. The default analysis begins with deterministic segmentation and optionally enriches the first 40 scenes. It is not a complete autonomous episode writer.

**ResearchRequirement:** scene/unit linkage, script excerpt, purpose, asset type, entity/aliases, chronology/location, edition fields, matching/rejection conditions, evidence and quality requirements, priority, status, selected asset ID. Fields being present does not prove their constraints are enforced.

**SourceAccess:** URL, access classification, resource type, hash, size, timestamps, errors. A `full_text` classification inferred from HTTP/type does not prove access to the full underlying publication.

**Evidence:** source reference, excerpt, location, requirement linkage. A reference ID or empty excerpt is not substantive evidence.

**CandidateAsset:** provenance URLs, hash, metadata, quality/usage information, requirement/scene relationships, review state and derivatives. Requested identity must remain distinct from independently established asset identity.

**Plan:** canvas, frame rate, language, scenes, durations or frame counts, narration/audio references, and elements. Elements contain type, rectangle, text/asset reference, appearance and applicable timing fields.

**StrokeDoc/Stroke:** geometric paths, cumulative lengths, brush profiles, pen lifts and metadata. These encode drawing, not semantic understanding.

**Narration manifest/alignment:** stored and original paths, audio fingerprint/probe information, sample boundaries, method and confidence. Current alignment is explicitly approximate.

## 7. Models and their actual roles

Qwen weights are currently referenced at:

`D:\withbord inmation\studio\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf`

The current Studio launcher selects 4B with an 8192-token context and a local endpoint normally on port 11435. These are configured values, not proof of a live server or its loaded weights during this documentation pass.

Two language clients coexist:

1. `providers/llm.py`: `auto` prefers an external key when present; the local branch lacks Authorization; availability accepts HTTP responses below 500, including authentication rejection.
2. `research/assistant.py`: bounded research tasks with authentication and explicit 401/403/error states. A successful model-list response and a local weight path do not conclusively establish the loaded weight identity. Schema checking is limited.

The newer workflow actually uses query drafting. Helper methods for extraction/comparison/next actions are not all integrated into its execution loop.

SD1.5 generates optional static assets via an isolated CPU worker, internally at 512px before output preparation. It is not a video generator or an authenticity checker. Procedural generators are preferred for paper, text-heavy layouts and predictable shapes.

Kokoro weights have been observed in the machine cache. Their presence is not proof of integrated, accepted narration production.

Historical evaluations found real limitations in local factual extraction, asset selection and autonomous workflows. A narrow native-tool search/download succeeded; this does not establish autonomous full-film production. See the audit report and protocol for exact conditions.

## 8. Research capabilities and important defects

Default discovery remains Wikipedia, Wikidata, Commons and the local library. There is no proven general-web discovery provider or integrated browser fallback. HTML reading is basic. PDF readers are optional; EPUB/IIIF code exists but live validation is not documented for them. OCR is not an accepted capability.

Saved WW1 evidence summary from 19 October reports: 15 requirements, 2 marked resolved, 13 unresolved, 13 candidates, 60 source-access records, zero downloads, assistant available, and time-budget exhaustion. This is a limited historical run, not a quality certificate.

Source-visible issues include:

- Candidate identity, edition, time and location are copied from the request and then used by verification. This is circular evidence.
- A `review_required` candidate can satisfy the current resolved check without approval.
- Mandatory aggregate gates include only identity, provenance and evidence; usage and evidence-content checks are insufficiently strict.
- Duplicate/visited handling can lose additional requirement relationships.
- User-source reader output is not fully incorporated into evidence and candidate extraction.
- Local documents are recorded and hashed without being read in that workflow path.
- Request accounting does not cover every underlying request; several budget settings are not enforced end-to-end.
- Resume budget state and the new workflow budget are not consistently unified.
- Redirect safety checks occur after automatic redirect following, rather than before every hop.
- New chronology helpers preserve BCE, while the older Wikidata year helper still uses absolute values and a restricted year range.
- Requirement fallback chronology/location can come from the first episode-wide value instead of the scene.

Do not describe this as complete deep research or treat every candidate as production-approved.

## 9. Asset Studio and rendering

Asset Studio has procedural generation, optional SD1.5, palette and text-zone processing, QA, manifests, previews and manual review state. `brain.py` is rule-based. QA measures appearance-related indicators; it does not establish historical or semantic correctness.

The inspected generated registry contains 15 assets: 13 procedural and 2 SD1.5, with zero approved. Approval metadata exists, but arbitrary renderer asset references are not universally blocked by a central approval gate.

Renderer support includes `background`, `texture`, and paper-card textures. Ordinary image elements convert through RGB/raster reveal; do not assume arbitrary RGBA cutout compositing or full object animation.

Text uses HarfBuzz/fontTools plus skeleton extraction and stroke ordering. English layout now advances words left-to-right, handles spacing, selects Inter/weights in English plans, and invalidates old text caches with pipeline version 6. This addresses the old word-reversal cause. It is not a full Unicode Bidi implementation or a fresh visual certification.

The Director creates a new board per scene, prepares elements, fits draw durations, follows active-element bounds, and streams frames. Text is fitted to its rectangle; line breaks largely come from the plan. The basic planner still takes the first 5/7/12 words and prefers the first available raster image.

Templates include highlighting, underlines, arrows, flourishes, timelines, bars, paper cards, torn strips and textures. They are building blocks, not a general editorial director.

## 10. Audio, timing and export

Narration import copies and fingerprints the source. Alignment distributes duration proportionally by text weights; it is not measured word-level alignment.

Writing SFX use `pen_ink.wav` and `pen_felt.wav` with provenance records describing real recordings. Ticks are short excerpts. Paper slide remains procedural noise. Synthetic fallback is possible when recordings are unavailable.

SFX hardening drops out-of-range events and closes open strokes, but Director still calculates:

```text
(scene_base + f)/fps + element_start + event_fraction * element_duration
```

Adding current local frame time on top of the event's element-relative position retains the previously identified timing defect. Dropping late events does not fix synchronization.

The rational timebase module already exists. The task is consistent use across consumers, not inventing it from scratch.

FFmpeg streams RGB frames into H.264 without storing the whole movie as frames. SFX still allocates a whole-duration float32 buffer and PCM16 conversion. Scene durations may extend to accommodate drawing. Reliable segment-based long-render recovery is not established.

FFmpeg lookup contains a fixed Studio runtime path followed by PATH. The writer uses overwrite mode and needs stronger output protection and failure cleanup. CLI adds SFX and media validation; the Studio bridge calls Director directly, so parity must not be assumed.

## 11. UI and standalone distribution

Repository `تشغيل-رسم.cmd` starts the root Python environment and `studio/launch.py`, which starts local services and opens port 8765.

Studio exposes understand/research/narration/plan/render routes. Its research bridge calls the older research stage. `rasm_to_studio_project` produces empty asset lists and a generic layout, losing information in the UI representation; this does not mean it deletes the original plan on disk.

Target: one project model, one job queue, reviewable evidence/assets, narration, preview, edit, export, cancel, resume, backup and restore. A tested installer/portable runtime independent of the development machine is not yet established.

## 12. Commands and side effects

These are developer reference examples, not commands executed for this handover. They write files and may access the network. Use a new disposable project and existing input paths.

From the primary project directory:

```powershell
.\.venv\Scripts\python.exe rasm.py understand "D:\inputs\script.txt" --project handover_demo --offline
.\.venv\Scripts\python.exe rasm.py research handover_demo --max-entities 5
.\.venv\Scripts\python.exe rasm.py audio handover_demo --file "D:\inputs\narration.wav"
.\.venv\Scripts\python.exe rasm.py plan handover_demo
.\.venv\Scripts\python.exe rasm.py validate projects/handover_demo/storyboard/plan.json --project projects/handover_demo
.\.venv\Scripts\python.exe rasm.py render handover_demo --fps 24 --size 1280x720 --max-seconds 30
```

Separate newer workflow and inspection commands:

```powershell
.\.venv\Scripts\python.exe rasm.py llm-status
.\.venv\Scripts\python.exe rasm.py evidence evidence_demo --script "D:\inputs\script.txt" --language en --max-seconds 120
.\.venv\Scripts\python.exe rasm.py assets doctor
.\.venv\Scripts\python.exe rasm.py assets kinds
```

`evidence` is not currently a drop-in replacement for the old research output. Actual configuration comes from configuration loading and environment overrides; an example config file is not proof of active settings. Never place credentials in documentation.

## 13. Evidence, tests and backups

Tests exist for assets, audio, mask equivalence, English plans/text, plan validation, research evidence, SFX and timebase. They were not run for this handover. Existing tests do not cover every identity false approval, entire-render synchronization or long-video failure mode.

Useful tools include `run_tests.py`, `qa_arabic.py`, `verify_raster_equiv.py`, `perf_phase31.py`, `bench_render.py`, and `build_ww1_v2.py`. The last tool authors a specific reference plan; it is not proof that Qwen autonomously designed that film.

Historical reference: `projects/ww1/render/preview_v2.mp4`, 81.5 seconds, 1956 frames, 720p24, SFX-only according to prior evidence. It was not re-probed here. The original v1 movie was overwritten; preserved stills and a plan replay are not the original binary.

Backups observed:

- Phase 3.1 bundle: 395,471,330 bytes.
- `backups/research-20261020/before.bundle`: 398,121,519 bytes, plus source fingerprints.

No complete restoration was established by this handover. Git excludes model weights, runtimes, generated assets and other data; a bundle alone is not a full recovery package. No remote was listed during inspection.

Pre-existing untracked safety work was present: `docs/06-STAGE-01-SAFETY-AR.md` and `tools/safety/`. Treat it as concurrent work. A safety plan is not a passed restore gate. Do not delete or indiscriminately commit these files.

## 14. Development order and acceptance

1. Complete backups, independent restore proof and measured baseline.
2. Unify project/time contracts and fix pen-event timing.
3. Correct research gates and connect approved selection to planning/UI.
4. Accept imported narration, replacement and alignment.
5. Add a small real-recording SFX library and reviewed mixing.
6. Improve explanation-driven plans, typography and purposeful motion.
7. Deliver a unified UI, queue, persistence and resumption.
8. Qualify 5/10/20/30-minute production progressively.
9. Package and test in a clean environment; inventory licenses/dependencies.
10. Measure comparable real episodes before committing to publication throughput.

Measure cold/warm preparation, rendering factor, sustained performance, RAM, storage, human review/rework, factual false approvals, false rejections and appropriate abstention. Do not treat a ranking score as a calibrated correctness probability.

Future contributors must inspect the current repository and instructions before editing. Preserve reference evidence and concurrent work, use isolated demonstrations, document limitations, and never weaken tests to satisfy optimistic completion claims.

**Bottom-line handover:** this is a real local rendering foundation with useful but partially integrated research and asset tooling. Reproducible professional production requires closing verification, timing, integration, recovery and distribution gaps—not replacing the engine or claiming unlimited model capability.
