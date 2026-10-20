# Rasm / Withbord Inmation

A local-first engine for explanatory videos built from whiteboard drawing, ink, paper, documentary collage, image reveals, a pen overlay, and camera movement. It renders a structured scene plan; it is not a neural text-to-video generator.

> **Status:** work in progress. Stage 0/1 safety work is in place, but the Stage 1 sign-off is pending an external backup copy. Stage 2 (project contract, rational timebase, packaging spike) is complete conditionally; owner sign-off and license review are still pending. This is not a production-ready release.
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

The CLI exposes `understand`, `research`, `evidence`, `plan`, `validate`, `render`, `audio`, `assets`, and related commands. Use `python rasm.py <command> --help` for the current arguments.

Project manifests are optional for legacy projects. A migrated project uses `project.json` as its entry point, with a relative active-plan path and hashes:

```powershell
python rasm.py project migrate ww1          # dry run
python rasm.py project migrate ww1 --apply  # backup, then write project.json
python rasm.py project validate ww1
```

Stage 2 evidence is in `rasm-pro/qa/stage2/` and the packaging decision is in `rasm-pro/docs/08-PACKAGING-ADR-AR.md`. The packaging spike is reproducible with `python tools/build_portable.py` (requires PyInstaller); it is not the final installer.

## Data, evidence, and large files

- The large icon manifest `rasm-pro/library/manifest-icons.jsonl` is stored with Git LFS. Run `git lfs pull` after cloning if the library is needed.
- Models, runtime binaries, backups, generated videos, frames, caches, and local project media are intentionally excluded from Git. The small Stage 2 QA clips under `rasm-pro/qa/stage2/` are the exception; they are verification evidence, not production media.
- Retrieved assets require human review and approval before production use.
- Generated artwork is illustration, not historical evidence. Qwen is an assistant, not a factual or permissions authority.
- There is no silent cloud or paid fallback.

## Current scope

The near-term target is a standalone, one-click Windows application for English-first episodes (Arabic support preserved), with sequential heavy jobs and explicit unresolved states. Animated presenters, CPU training, and 4K/60 fps are outside the initial release.

## License

No license has been selected yet. Do not assume permission to redistribute third-party assets included for development; check the relevant credits and licenses.

---

# راسم — محرك فيديو الوايت بورد

محرك محلي لبناء فيديوهات تفسيرية بالرسم على الوايت بورد، الحبر، الورق، الكولاج، كشف الصور، والقلم والكاميرا. المحرك يرندر خطة مشاهد منظمة، وليس مولد فيديو عصبيًا.

**الحالة:** المشروع قيد التطوير. خطوط الأمان الأساسية موجودة، لكن توقيع المرحلة الأولى معلّق حتى النسخ على وسيط خارجي. المرحلة الثانية (عقد المشروع، التوقيت العقلاني، تجربة التغليف) مكتملة شرطيًا؛ توقيع المالك ومراجعة التراخيص ما زالا معلّقين. ليس إصدارًا جاهزًا للإنتاج.

- المحرك الأساسي في `rasm-pro/`.
- واجهة الاستوديو والجسر المحلي في `studio/`.
- النماذج والملفات الضخمة والنسخ الاحتياطية والفيديوهات المولدة غير مرفوعة إلى Git، باستثناء مقطعي التحقق الصغيرين في `rasm-pro/qa/stage2/`.
- ملف الأيقونات الكبير `manifest-icons.jsonl` محفوظ عبر Git LFS.
- الأصول المسترجعة تحتاج مراجعة بشرية قبل الاستخدام، والصور المولدة ليست دليلًا تاريخيًا.
- أدلة المرحلة الثانية في `rasm-pro/qa/stage2/`، وقرار التغليف في `rasm-pro/docs/08-PACKAGING-ADR-AR.md`.
- لا يوجد تحويل صامت إلى خدمات سحابية أو مدفوعة.
