# Rasm / Withbord Inmation

A local-first engine for explanatory videos built from whiteboard drawing, ink, paper, documentary collage, image reveals, a pen overlay, and camera movement. It renders a structured scene plan; it is not a neural text-to-video generator.

> **Status:** work in progress. Stage 2 (project contract, rational timebase, packaging spike) is complete and signed by the owner; the license audit is closed. Stage 3 (assets inside the plan + human approval gate) is implemented and awaiting owner sign-off. The Stage 1 external backup copy is still open — no external medium is attached. This is not a production-ready release.
>
> **Repository:** <https://github.com/coocdv-cmyk/withbord-aldahihe7>

## Repository map

| Path | Purpose |
|---|---|
| `rasm-pro/` | Primary Python engine: CLI, planning, research, assets, strokes, renderer, audio, tests, and docs. |
| `studio/` | Local UI bridge and runtime integration. |
| `gen/`, `test/`, `projects/` | Supporting experiments, test material, and production project data. |
| `rasm-pro/docs/` | Stage reports, engineering notes, and handover documents. |
| `rasm-pro/future-character-assets/` | Exploratory character/asset work; not part of the v1 animated-presenter scope. |

## Requirements

- Windows 10/11. The reference machine is an Intel i5-1135G7, 16 GB RAM, Intel Iris Xe; do not assume a discrete GPU or CUDA.
- Python 3.13 for running from source (the current virtual environment uses 3.13.15). The packaging spike produces a one-folder executable that does not require Python at runtime.
- FFmpeg/ffprobe. Resolution order: `RASM_FFMPEG`, `RASM_FFMPEG_DIR`, a `runtime/` folder beside the executable, `RASM_HOME/runtime`, the source `studio/runtime/`, then `PATH`.
- Optional: a local Qwen 3 4B GGUF model for bounded assistance. Models are **not** included in this repository and must not be downloaded silently.

## Quick start

```powershell
cd rasm-pro
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python rasm.py --help
```

The CLI exposes `understand`, `research`, `evidence`, `plan`, `validate`, `render`, `audio`, `assets`, `approvals`, and related commands. Use `python rasm.py <command> --help` for the current arguments.

Retrieved assets need a **human** decision before they can appear in a production
render. The decision log is append-only, the manifest is only a projection of it,
and a production render is refused while an asset it uses is unapproved:

```powershell
python rasm.py approvals list ww1              # every asset + its state
python rasm.py approvals gate ww1              # would a production render pass?
python rasm.py approvals approve ww1 --asset a-c75888b731eb --by "your name"
python rasm.py approvals import ww1            # pull research/assets.json into the manifest
python rasm.py project link-assets ww1         # relative asset paths + asset_id in the plan
python rasm.py render ww1                      # production: refused while assets are pending
python rasm.py render ww1 --preview            # preview: warns instead of blocking
```

Generated artwork is never treated as historical evidence, and a rejected asset
blocks in every mode.

### Narration: measured loudness, measured alignment

```powershell
python rasm.py audio ww1 --file "C:\path\narration.wav"  # import + measure + align
python rasm.py audio ww1                                  # loudness + alignment report
python rasm.py audio ww1 --align                          # re-run the measured alignment
python rasm.py audio ww1 --normalize -16                  # explicit, logged normalization
```

Loudness is measured with ITU-R BS.1770-4 (integrated LUFS, LRA, true peak) and
the scene boundaries come from the **measured** audio samples, so the picture
follows the voice. A production render is refused while the narration is
unmeasured, off target, or shorter than the picture — never trimmed silently.

### Continuous integration

A reviewed CI workflow is kept at `rasm-pro/tools/ci/ci.yml` with the
activation steps in `rasm-pro/tools/ci/README.md`. It runs a compile check and
the full test suite on Ubuntu with Python 3.13; tests that need ffmpeg are
skipped explicitly when the tool is absent, so a clean runner still gives a
meaningful result.

Project manifests are optional for legacy projects. A migrated project uses `project.json` as its entry point, with a relative active-plan path and hashes:

```powershell
python rasm.py project migrate ww1          # dry run
python rasm.py project migrate ww1 --apply  # backup, then write project.json
python rasm.py project validate ww1
```

Stage 2 evidence is in `rasm-pro/qa/stage2/` and the packaging decision is in `rasm-pro/docs/08-PACKAGING-ADR-AR.md`. The packaging spike is reproducible with `python tools/build_portable.py` (requires PyInstaller); it is not the final installer. Stage 3 evidence (approval gate) is in `rasm-pro/qa/stage3/` and its contract is `rasm-pro/docs/09-STAGE-03-CONTRACT-AR.md`.

## Data, evidence, and large files

- The large icon manifest `rasm-pro/library/manifest-icons.jsonl` is stored with Git LFS. Run `git lfs pull` after cloning if the library is needed.
- Models, runtime binaries, backups, generated videos, frames, caches, and local project media are intentionally excluded from Git. The small Stage 2/3 QA clips under `rasm-pro/qa/` are the exception; they are verification evidence, not production media.
- Retrieved assets require human review and approval before production use.
- Generated artwork is illustration, not historical evidence. Qwen is an assistant, not a factual or permissions authority.
- There is no silent cloud or paid fallback.

## Current scope

The near-term target is a standalone, one-click Windows application for English-first episodes (Arabic support preserved), with sequential heavy jobs and explicit unresolved states. Animated presenters, CPU training, and 4K/60 fps are outside the initial release.

## License

The project code is MIT-licensed (see `LICENSE`). Third-party components keep
their own terms — fonts (OFL-1.1 / Apache-2.0), Python dependencies, the local
Qwen model (Apache-2.0, not redistributed), and ffmpeg (a GPL build that is
deliberately **not** bundled; it is an external sidecar). The full audit is in
`rasm-pro/docs/10-LICENSE-AUDIT-AR.md` and `THIRD_PARTY_NOTICES.md`.

---

# راسم — محرك فيديو الوايت بورد

محرك محلي لبناء فيديوهات تفسيرية بالرسم على الوايت بورد، الحبر، الورق، الكولاج، كشف الصور، والقلم والكاميرا. المحرك يرندر خطة مشاهد منظمة، وليس مولد فيديو عصبيًا.

**الحالة:** المشروع قيد التطوير. توقيع المرحلة الثانية مكتمل من المالك (20 أكتوبر 2026)، لكن بند **النسخة الخارجية** للمرحلة الأولى ما زال مفتوحًا (لا يوجد وسيط خارجي موصول). تدقيق التراخيص اكتمل في `rasm-pro/docs/10-LICENSE-AUDIT-AR.md`. المرحلة الثالثة (الأصول داخل الخطة + بوابة الاعتماد البشري) منفَّذة وبانتظار توقيع المالك. ليس إصدارًا جاهزًا للإنتاج.

- المحرك الأساسي في `rasm-pro/`.
- واجهة الاستوديو والجسر المحلي في `studio/`.
- النماذج والملفات الضخمة والنسخ الاحتياطية والفيديوهات المولدة غير مرفوعة إلى Git، باستثناء مقاطع التحقق الصغيرة في `rasm-pro/qa/`.
- ملف الأيقونات الكبير `manifest-icons.jsonl` محفوظ عبر Git LFS.
- الأصول المسترجعة تحتاج مراجعة بشرية قبل الاستخدام، والصور المولدة ليست دليلًا تاريخيًا.
- أدلة المرحلة الثانية في `rasm-pro/qa/stage2/`، وقرار التغليف في `rasm-pro/docs/08-PACKAGING-ADR-AR.md`، وعقد المرحلة الثالثة في `rasm-pro/docs/09-STAGE-03-CONTRACT-AR.md` وأدلتها في `rasm-pro/qa/stage3/`.
- لا يوجد تحويل صامت إلى خدمات سحابية أو مدفوعة.

### اعتماد الأصول (المرحلة الثالثة)

```powershell
python rasm.py approvals list ww1              # كل الأصول وحالة الاعتماد
python rasm.py approvals gate ww1              # هل يمرّ رندر إنتاجي؟
python rasm.py approvals approve ww1 --asset a-c75888b731eb --by "اسم المراجع"
python rasm.py approvals import ww1            # دمج أصول البحث في المانيفست
python rasm.py project link-assets ww1         # مسارات نسبية + asset_id في الخطة
python rasm.py render ww1                      # إنتاج: يُمنع مع أصل غير معتمد
python rasm.py render ww1 --preview            # معاينة: تحذير بدل المنع
```

سجل القرارات `research/approvals.jsonl` **append-only**، والمانيفست إسقاط له فقط.
الأصل المرفوض يمنع في كل الأوضاع، والمولَّد لا يُعتمد كدليل.
