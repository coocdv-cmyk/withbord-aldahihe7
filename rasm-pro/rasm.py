#!/usr/bin/env python
"""rasm — واجهة سطر الأوامر للمحرك (فهم → بحث → مسارات → معاينة)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.core.assets import (  # noqa: E402
    ApprovalError,
    append_decision,
    evaluate_gate,
    link_plan_assets,
    plan_asset_refs,
    sync_manifest_approvals,
)
from engine.core.log import get_logger  # noqa: E402
from engine.core.paths import ROOT as DATA_ROOT, project_dir  # noqa: E402
from engine.core.plan_time import plan_frame_rate  # noqa: E402
from engine.core.project import (  # noqa: E402
    ProjectError,
    activate_plan,
    build_asset_entries,
    infer_manifest,
    load_active_plan,
    manifest_plan_path,
    plan_has_absolute_paths,
    project_manifest_path,
    read_manifest,
    relative_project_path,
    utc_now,
    validate_manifest,
    write_manifest,
)
from engine.core.timebase import FrameRate, TimebaseError, coerce_frame_rate  # noqa: E402
from engine.core.util import read_json, write_json  # noqa: E402
from engine.render import Director  # noqa: E402
from engine.stages import plan as plan_stage  # noqa: E402
from engine.stages import research as research_stage  # noqa: E402
from engine.stages import understanding as understanding_stage  # noqa: E402
from engine.stages.validate_plan import validate_plan  # noqa: E402
from engine.strokes import (  # noqa: E402
    find_font,
    raster_to_strokes,
    render_preview,
    render_strip,
    scan_svg,
    text_to_strokes,
)

log = get_logger("cli")


def _try_manifest(pd: Path) -> dict | None:
    """Read the manifest but keep legacy projects usable before migration."""
    if not project_manifest_path(pd).exists():
        return None
    return read_manifest(pd, required=True)


def _resolve_plan_arg(pd: Path, explicit: str | None = None) -> Path:
    if explicit:
        raw = Path(explicit)
        candidates = [raw] if raw.is_absolute() else [
            pd / raw,
            pd / "storyboard" / raw,
            pd / "storyboard" / raw.name,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise FileNotFoundError(f"ملف الخطة غير موجود: {explicit}")
    man = _try_manifest(pd)
    if man:
        path = manifest_plan_path(pd, man)
        # Verify the manifest hash before the renderer reads it.
        load_active_plan(pd, man)
        return path
    for name in ("plan_v2.json", "plan.json"):
        candidate = pd / "storyboard" / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError("لا توجد خطة نشطة — شغّل: rasm plan")


def _project_rate(pd: Path, explicit: str | None = None) -> FrameRate:
    """Project override first, then active plan, then the 24fps default."""
    if explicit:
        return coerce_frame_rate(explicit)
    man = _try_manifest(pd)
    if man and man.get("fps") is not None:
        return coerce_frame_rate(man["fps"])
    try:
        plan_path = _resolve_plan_arg(pd)
        plan = read_json(plan_path) or {}
        return plan_frame_rate(plan)
    except (FileNotFoundError, TimebaseError):
        return FrameRate(24)


def _manifest_equivalent(a: dict, b: dict) -> bool:
    left = {k: v for k, v in a.items() if k != "updated_at"}
    right = {k: v for k, v in b.items() if k != "updated_at"}
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(
        right, ensure_ascii=False, sort_keys=True
    )


def _write_migration_backup(pd: Path, pid: str) -> Path:
    stamp = utc_now().replace(":", "").replace("-", "").replace("T", "-").replace("Z", "")
    dest = DATA_ROOT.parent / "backups" / "project-migrations" / f"{pid}-{stamp}"
    dest.mkdir(parents=True, exist_ok=False)
    existing = project_manifest_path(pd)
    if existing.exists():
        (dest / "project.json.before").write_bytes(existing.read_bytes())
    inventory = {}
    for label, rel in (
        ("script", "script/scriptgraph.json"),
        ("research", "research/research.json"),
        ("assets_index", "research/assets.json"),
        ("plan_v2", "storyboard/plan_v2.json"),
        ("plan", "storyboard/plan.json"),
        ("narration", "audio/narration.json"),
        ("alignment", "audio/alignment.json"),
    ):
        p = pd / rel
        if p.exists():
            from engine.core.util import sha256_file

            inventory[label] = {"path": rel, "sha256": sha256_file(p), "bytes": p.stat().st_size}
    (dest / "inventory.before.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dest


def _apply_manifest(pd: Path, manifest: dict) -> tuple[dict, bool]:
    """Write a manifest atomically; validate before and after. Returns (report, changed)."""
    old = read_manifest(pd)
    if old is not None:
        if _manifest_equivalent(old, manifest):
            return validate_manifest(old, pd), False
        manifest = dict(manifest)
        manifest["created_at"] = old.get("created_at") or manifest.get("created_at")
    backup = _write_migration_backup(pd, str(manifest.get("project_id") or pd.name))
    write_manifest(pd, manifest)
    loaded = read_manifest(pd, required=True)
    report = validate_manifest(loaded, pd)
    if not report["ok"]:
        if old is not None:
            write_manifest(pd, old)
        else:
            try:
                project_manifest_path(pd).unlink()
            except FileNotFoundError:
                pass
        raise ProjectError(
            "فشل التحقق بعد كتابة المانيفست — تم التراجع. "
            + "; ".join(report["errors"][:5])
        )
    print(f"• نسخة ما قبل الترحيل: {backup}")
    return report, True


def cmd_understand(args) -> int:
    script = Path(args.script).read_text(encoding="utf-8")
    graph = understanding_stage.analyze_script(script, force_offline=args.offline)
    pd = project_dir(args.project)
    out = understanding_stage.save_graph(graph, pd)
    (pd / "script" / "script.txt").write_text(script, encoding="utf-8")
    print(f"✔ التحليل محفوظ: {out}")
    print(f"  المحرك: {graph.get('engine')} · لغة: {graph.get('lang')} · مشاهد: {graph['stats'].get('scenes')} · مدة ≈ {graph['stats'].get('estimated_duration')}ث")
    print(f"  كيانات: {len(graph.get('entities', []))} · ادّعاءات: {len(graph.get('claims', []))}")
    for e in graph.get("entities", [])[:8]:
        print(f"   - [{e.get('type')}] {e.get('name')} → {', '.join(e.get('needs', []))}")
    return 0


def cmd_research(args) -> int:
    pd = project_dir(args.project)
    graph = read_json(pd / "script" / "scriptgraph.json")
    if not graph:
        print("✘ لا يوجد scriptgraph.json — شغّل: rasm understand أولا")
        return 1
    res = research_stage.research_script(graph, pd, max_entities=args.max_entities, download=not args.no_download)
    print(f"✔ البحث محفوظ: {pd / 'research' / 'research.json'}")
    print(f"  تنزيل: {res['totals']['downloaded']} · إعادة استخدام: {res['totals']['reused']} · مرفوض: {res['totals']['denied']}")
    for e in res["entities"]:
        print(f"   - {e['name']}: {len(e['assets'])} أصل" + (" (حقائق ويكي بيانات ✓)" if e.get("facts") else ""))
    return 0


def cmd_evidence(args) -> int:
    from engine.research.assistant import load_assistant_config, ResearchAssistant
    from engine.research.workflow import ResearchWorkflow
    from engine.research.evidence import ResearchBudget

    pd = project_dir(args.project)
    script_text = None
    srt_text = None
    if args.script:
        script_text = Path(args.script).read_text(encoding="utf-8")
    elif args.srt:
        srt_text = Path(args.srt).read_text(encoding="utf-8")
    else:
        script_path = pd / "script" / "script.txt"
        if script_path.exists():
            script_text = script_path.read_text(encoding="utf-8")
        else:
            graph = read_json(pd / "script" / "scriptgraph.json")
            if graph:
                script_text = "\n".join(s.get("narration", "") for s in graph.get("scenes", []))

    budget = ResearchBudget(
        max_seconds=args.max_seconds,
        max_requests=args.max_requests,
        max_pages=args.max_pages,
        max_downloads=args.max_downloads,
        max_download_bytes=args.max_download_bytes,
        max_depth=args.max_depth,
        max_llm_calls=args.max_llm_calls,
        max_llm_tokens=args.max_llm_tokens,
        concurrency=args.concurrency,
        resume=not args.no_resume,
    )
    store = None
    if args.download:
        from engine.research.store import AssetStore
        from engine.research.http import HttpClient

        store = AssetStore(pd, HttpClient("rasm-pro research (local)", timeout=45))
    assistant = ResearchAssistant(load_assistant_config())
    workflow = ResearchWorkflow(
        pd,
        budget=budget,
        assistant=assistant,
        download=args.download,
        resume=not args.no_resume,
        store=store,
    )
    state = workflow.run(
        script_text=script_text,
        srt_text=srt_text,
        source_urls=list(args.source_url or []),
        local_documents=list(args.doc or []),
        language=args.language,
        download=args.download,
    )
    print("EVIDENCE STATUS:", state.status)
    print("requirements:", len(state.requirements), "resolved:", sum(1 for r in state.requirements if r.status == "resolved"), "unresolved:", sum(1 for r in state.requirements if r.status != "resolved"))
    print("sources:", len(state.sources), "candidates:", len(state.candidates), "assistant:", state.assistant_status)
    print("output:", pd / "research" / "evidence.json")
    if state.warnings:
        for w in state.warnings[:10]:
            print("WARNING:", w)
    if state.errors:
        for e in state.errors[:10]:
            print("ERROR:", e, file=sys.stderr)
    return 0 if state.status == "completed" else 2


def cmd_llm_status(args) -> int:
    from engine.research.assistant import load_assistant_config, ResearchAssistant

    assistant = ResearchAssistant(load_assistant_config())
    status = assistant.probe()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status.get("available") else 2


def cmd_strokes(args) -> int:
    out = Path(args.out) if args.out else DATA_ROOT / "cache" / "preview.png"
    if args.text:
        font = find_font(args.font or "arefruqaa")
        doc = text_to_strokes(args.text, font, args.size, mode=args.mode)
    else:
        p = Path(args.path or "")
        if not p.exists():
            print("✘ مسار غير موجود")
            return 1
        if p.suffix.lower() == ".svg":
            doc = scan_svg(p)
        else:
            import numpy as np
            from PIL import Image

            arr = np.asarray(Image.open(p).convert("RGB"))
            doc = raster_to_strokes(arr)
    doc.save(out.with_suffix(".rstrokes.json"))
    if args.strip:
        render_strip(doc, out, steps=6)
    else:
        render_preview(doc, out, canvas=(1400, 900))
    print(f"✔ {len(doc.strokes)} مسار · طول كلي {doc.total_length():.0f} · معاينة: {out}")
    return 0


def cmd_icons(args) -> int:
    from engine.research.local_library import search_icons

    icons = search_icons(args.keywords, limit=args.limit)
    print(f"نتائج: {len(icons)}")
    for ic in icons:
        print(f" - {ic['id']} · {ic.get('license')} · {ic.get('style')} · {ic['file']}")
    return 0


def cmd_audio(args) -> int:
    from engine.audio import baseline_align, import_narration, save_alignment

    pd = project_dir(args.project)
    try:
        man = import_narration(pd, args.file, copy=not args.no_copy, note=args.note or "")
    except Exception as e:
        print(f"✘ فشل استيراد الصوت: {e}")
        return 1
    dur = man.get("duration_exact") or man.get("duration")
    print(f"✔ التعليق محفوظ: {man['path']}")
    print(
        f"  {man.get('codec')} · {man.get('sample_rate')} هرتز · {man.get('channels')} قناة · "
        f"عينات {man.get('total_samples')} · مدة {dur}ث"
    )
    print(f"  بصمة: {man['sha256'][:16]}… · الأصل: {man['original']['name']} (لم يُعدَّل)")

    graph = read_json(pd / "script" / "scriptgraph.json")
    if graph and man.get("total_samples") and man.get("sample_rate"):
        al = baseline_align(graph.get("scenes", []), int(man["total_samples"]), int(man["sample_rate"]))
        out = save_alignment(al, pd)
        sr = int(man["sample_rate"])
        print(f"✔ محاذاة تقديرية صريحة ({al.level}): {out}")
        for seg in al.segments:
            print(
                f"   - مشهد {seg.scene_id}: "
                f"[{seg.start_sample / sr:.2f} → {seg.end_sample / sr:.2f}]ث · ثقة {seg.confidence:.2f}"
                + (" ⚠ " + ",".join(seg.flags) if "rate-extreme" in seg.flags else "")
            )
        print("  ملاحظة: التوقيت مرجعه عينات الصوت، لكن توزيعه على المشاهد تقديري.")
    else:
        print("• لا يوجد scriptgraph.json — تم استيراد الصوت فقط (شغّل understand ثم أعد audio).")
    return 0


def cmd_plan(args) -> int:
    pd = project_dir(args.project)
    graph = read_json(pd / "script" / "scriptgraph.json")
    if not graph:
        print("✘ لا يوجد scriptgraph.json — شغّل: rasm understand أولا")
        return 1
    research = read_json(pd / "research" / "research.json", default={}) or {}
    try:
        rate = _project_rate(pd, getattr(args, "fps", None))
    except TimebaseError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    plan = plan_stage.build_plan(
        graph, research, project_dir=pd, max_scenes=args.max_scenes, fps=rate
    )
    report = validate_plan(plan, project_dir=pd)
    for warning in report["warnings"][:8]:
        print(f"⚠ {warning}")
    if not report["ok"]:
        for error in report["errors"][:12]:
            print(f"✘ {error}", file=sys.stderr)
        print(f"✘ الخطة المبنية غير صالحة ({len(report['errors'])} خطأ)", file=sys.stderr)
        return 2
    out = plan_stage.save_plan(plan, pd)
    if _try_manifest(pd) is not None:
        try:
            activate_plan(pd, out)
        except ProjectError as exc:
            print(f"✘ حُفظت الخطة لكن تعذّر تنشيطها: {exc}", file=sys.stderr)
            return 2
    print(f"✔ الخطة محفوظة: {out} · {rate} · {plan['stats'].get('frames')} إطار")
    timing = plan.get("timing") or {}
    if timing.get("source"):
        lvl = timing.get("level") or "-"
        print(f"  التوقيت: {timing['source']} · مستوى {lvl} · {timing.get('method', '')}")
    print(f"  مشاهد: {plan['stats']['scenes']} · عناصر: {plan['stats']['elements']} · مدة ≈ {plan['stats']['estimated_duration']}ث")
    for s in plan["scenes"][:6]:
        kinds = ", ".join(e["type"] for e in s["elements"]) or "—"
        print(f"   - مشهد {s['id']}: {len(s['elements'])} عنصر ({kinds}) · {s['duration']}ث · {s['narration'][:60]}")
    return 0


def cmd_render(args) -> int:
    pd = project_dir(args.project)
    try:
        plan_path = _resolve_plan_arg(pd, getattr(args, "plan", None))
        plan = read_json(plan_path)
    except FileNotFoundError:
        plan = None
        plan_path = pd / "storyboard" / "plan.json"
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    if not plan:
        graph = read_json(pd / "script" / "scriptgraph.json")
        if not graph:
            print("✘ لا يوجد تحليل — شغّل: rasm understand ثم rasm plan")
            return 1
        research = read_json(pd / "research" / "research.json", default={}) or {}
        try:
            rate = _project_rate(pd, getattr(args, "fps", None))
        except TimebaseError as exc:
            print(f"✘ {exc}", file=sys.stderr)
            return 2
        plan = plan_stage.build_plan(graph, research, project_dir=pd, fps=rate)
        auto_report = validate_plan(plan, project_dir=pd)
        if not auto_report["ok"]:
            for error in auto_report["errors"][:20]:
                print(f"✘ {error}", file=sys.stderr)
            print(
                f"✘ الخطة المبنية تلقائيًا غير صالحة ({len(auto_report['errors'])} خطأ) — لم تُحفظ",
                file=sys.stderr,
            )
            return 2
        try:
            plan_path = plan_stage.save_plan(plan, pd)
            if _try_manifest(pd) is not None:
                activate_plan(pd, plan_path)
        except ProjectError as exc:
            print(f"✘ تعذّر حفظ/تنشيط الخطة: {exc}", file=sys.stderr)
            return 2
        print(f"• تم بناء الخطة تلقائيًا: {plan_path} ({rate})")

    if not getattr(args, "skip_validate", False):
        report = validate_plan(plan, project_dir=pd)
        for warning in report["warnings"][:10]:
            print(f"⚠ {warning}")
        if not report["ok"]:
            for error in report["errors"][:20]:
                print(f"✘ {error}", file=sys.stderr)
            print(f"✘ الخطة غير صالحة ({len(report['errors'])} خطأ) — لم يبدأ الرندر", file=sys.stderr)
            return 2

    # بوابة الاعتماد: رندر الإنتاج لا يستخدم أصلًا غير معتمد
    preview_mode = bool(getattr(args, "preview", False)) or args.max_seconds is not None
    mode = "preview" if preview_mode else "final"
    manifest = _try_manifest(pd)
    if manifest is not None:
        try:
            gate = evaluate_gate(plan, pd, manifest=manifest, mode=mode)
        except ApprovalError as exc:
            print(f"✘ {exc}", file=sys.stderr)
            return 2
        for item in gate.warnings[:12]:
            print(f"⚠ {item['reason']}: {item['path'] or item['display']} — {item['detail']}")
        if not gate.ok:
            print("✘ بوابة الأصول: الرندر النهائي ممنوع", file=sys.stderr)
            for item in gate.blocking[:20]:
                print(
                    f"   ✘ {item['reason']}: {item['path'] or item['display']} — {item['detail']}",
                    file=sys.stderr,
                )
            print(
                "   • اعتمد الأصل: rasm approvals approve <project> --asset <path> --by <name>",
                file=sys.stderr,
            )
            print("   • أو معاينة فقط: --preview (أو --max-seconds)", file=sys.stderr)
            return 2
        pending = [i for i in gate.used if i["state"] != "approved"]
        if preview_mode and pending:
            print(f"ℹ معاينة: {len(pending)} أصلًا غير معتمد — مسموح في المعاينة، ممنوع في الإنتاج")

    out = Path(args.out) if args.out else pd / "render" / "preview.mp4"
    size = (1280, 720)
    if args.size:
        try:
            w, h = args.size.lower().split("x")
            size = (int(w), int(h))
        except Exception:
            print("✘ حجم غير صالح — استخدم مثل 1280x720")
            return 1
    scene_range = None
    if args.scenes:
        try:
            a, b = args.scenes.split("-")
            scene_range = (int(a), int(b))
        except Exception:
            scene_range = (1, int(args.scenes))

    canvas = tuple(plan.get("canvas") or [2560, 1440])

    # الصوت: من الخطة أو --audio أو narration.json في المشروع
    audio_file = None
    plan_audio = plan.get("audio") or {}
    if getattr(args, "audio", None):
        audio_file = args.audio
    elif plan_audio.get("file"):
        candidate = Path(plan_audio["file"])
        if not candidate.is_absolute():
            candidate = pd / candidate
        if candidate.exists():
            audio_file = candidate
    if audio_file is None:
        from engine.audio import load_narration

        nar = load_narration(pd)
        if nar:
            audio_file = nar.get("path")
    if audio_file:
        print(f"• سرد صوتي: {Path(audio_file).name}")

    try:
        director = Director(
            plan,
            canvas=canvas,
            out_size=size,
            fps=getattr(args, "fps", None),
            crf=args.crf,
            project_dir=pd,
        )
    except TimebaseError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    print(f"• الخطة: {plan_path} · معدل: {director.fps_rate} · حدود مطلقة")
    res = director.render(out, audio=audio_file, max_seconds=args.max_seconds, scene_range=scene_range)
    print(f"✔ الفيديو: {res['out']}")
    print(
        f"  {res['frames']} إطار · {res['seconds']}ث · "
        f"{res.get('fps')} · زمن الرندر {res['render_seconds']}ث"
    )
    if res.get("overflow_scenes"):
        print(f"⚠ مشاهد تجاوز الرسمُ مدتها (لن تُمدّ): {res['overflow_scenes']}")

    # مؤثرات صوتية واقعية من أحداث القلم (تُدمج في نفس ملف الفيديو)
    sfx_muxed = False
    if getattr(args, "sfx", True) and res.get("sfx") and Path(res["sfx"]).exists():
        try:
            from engine.audio.sfx import build_track, mux_into

            wav = Path(str(out)).with_suffix(".sfx.wav")
            info = build_track(
                res["sfx"], wav, preset=getattr(args, "sfx_preset", "paper"),
                duration=res["seconds"]
            )
            mux = mux_into(out, wav, out, narration=None, duration=res["seconds"])
            res["sfx_wav"] = str(wav)
            res["audio_mode"] = mux["mode"]
            sfx_muxed = True
            src = "تسجيلات حقيقية (ملكية عامة)" if info.get("real_recordings") else "توليف احتياطي"
            print(f"• مؤثرات: {info['scratches']} رسمة · {info['taps']} نقرة · {info['slides']} انزلاق · {src} · دمج: {mux['mode']}")
        except Exception as e:
            print(f"⚠ تعذّر إدماج المؤثرات الصوتية: {e}")
    if res.get("narration_frames") is not None:
        drift = res.get("drift_frames")
        print(f"  مزامنة السرد: {res['narration_frames']} إطار متوقع · انزلاق {drift} إطار {'✔' if drift == 0 else '⚠'}")

    # تحقق رقمي مستقل (FFprobe) — لا نجاح بلا دليل
    from engine.render.validate import validate_video

    report = validate_video(
        out,
        expect_size=size,
        expect_fps=director.fps_rate,
        expect_frames=res["frames"],
        expect_audio=bool(audio_file) or sfx_muxed,
        expect_duration_sec=res["duration_sec_exact"],
        tolerance_frames=1,
    )
    print(("✔" if report["ok"] else "✘") + f" تحقق FFprobe: {report['path']}")
    for c in report["checks"]:
        print(f"   {'✔' if c['ok'] else '✘'} {c['check']}: {c['detail']}")
    return 0 if report["ok"] else 2


def cmd_project_init(args) -> int:
    pd = project_dir(args.project)
    try:
        existing = read_manifest(pd)
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    if existing is not None and not args.force:
        print(f"✘ المانيفست موجود: {project_manifest_path(pd)} — استخدم --force", file=sys.stderr)
        return 2
    try:
        manifest = infer_manifest(
            pd,
            project_id=pd.name,
            active_plan=args.plan,
            title=args.title,
            language=args.language,
            now=utc_now(),
        )
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    report = validate_manifest(manifest, pd)
    if not report["ok"]:
        for error in report["errors"][:20]:
            print(f"✘ {error}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        print("• dry-run: لم تتم الكتابة")
        return 0
    try:
        _apply_manifest(pd, manifest)
    except ProjectError as exc:
        print(f"✘ تعذّر كتابة المانيفست: {exc}", file=sys.stderr)
        return 2
    print(f"✔ المانيفست: {project_manifest_path(pd)}")
    return 0


def cmd_project_validate(args) -> int:
    pd = project_dir(args.project)
    try:
        manifest = read_manifest(pd, required=True)
        report = validate_manifest(manifest, pd)
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    print(("✔" if report["ok"] else "✘") + f" مانيفست المشروع: {project_manifest_path(pd)}")
    print(
        f"  أصول: {report['stats']['assets']} (معلّق: {report['stats']['pending_assets']}) · "
        f"رندرات: {report['stats']['renders']} · غير محسوم: {report['stats']['unresolved']}"
    )
    for warning in report["warnings"][:20]:
        print(f"⚠ {warning}")
    for error in report["errors"][:30]:
        print(f"✘ {error}", file=sys.stderr)
    return 0 if report["ok"] else 2


def cmd_project_migrate(args) -> int:
    pd = project_dir(args.project)
    try:
        existing = read_manifest(pd)
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    try:
        manifest = infer_manifest(
            pd,
            project_id=pd.name,
            active_plan=args.plan,
            title=args.title,
            language=args.language,
            now=utc_now(),
        )
    except (ProjectError, TimebaseError) as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    report = validate_manifest(manifest, pd)
    print(f"• المشروع: {pd}")
    print(
        f"• الخطة النشطة: {manifest['storyboard']['active']} · {manifest['fps']} · "
        f"{report['stats']['assets']} أصل · {report['stats']['renders']} رندر"
    )
    for warning in report["warnings"][:12]:
        print(f"⚠ {warning}")
    if not report["ok"]:
        for error in report["errors"][:30]:
            print(f"✘ {error}", file=sys.stderr)
        print("✘ الترحيل لم يبدأ — المانيفست المقترح غير صالح", file=sys.stderr)
        return 2
    if existing is not None and _manifest_equivalent(existing, manifest):
        print("✔ already migrated — لا تغيير")
        return 0
    if existing is not None and not args.force:
        print("✘ المانيفست موجود ويختلف — استخدم --force للتحديث", file=sys.stderr)
        return 2
    if not args.apply:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        print("• dry-run: لم تتم الكتابة (استخدم --apply)")
        return 0
    try:
        final_report, changed = _apply_manifest(pd, manifest)
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    print(f"✔ مانيفست المشروع: {project_manifest_path(pd)} · تغيير: {changed}")
    print(
        f"  أصول: {final_report['stats']['assets']} (معلّق: {final_report['stats']['pending_assets']}) · "
        f"غير محسوم: {final_report['stats']['unresolved']}"
    )
    return 0


# ---------------------------------------------------------------------------
# المرحلة 3 — اعتماد الأصول (بوابة الإنتاج)
# ---------------------------------------------------------------------------

_DECISION_WORDS = {"approve": "approved", "reject": "rejected", "defer": "deferred"}
_STATE_MARKS = {"approved": "✔", "rejected": "✘", "deferred": "…", "pending": "·"}


def _manifest_asset_by_token(pd: Path, manifest: dict, token: str) -> dict | None:
    """Find a manifest asset by asset id, exact path, or unique file name."""
    assets = [a for a in (manifest.get("assets") or []) if isinstance(a, dict)]
    token = str(token or "").strip()
    if not token:
        return None
    for asset in assets:
        if str(asset.get("asset_id") or "") == token:
            return asset
    rel = None
    try:
        rel = relative_project_path(pd, token)
    except ProjectError:
        rel = None
    for asset in assets:
        path = str(asset.get("path") or "")
        if path == token or (rel and path == rel):
            return asset
    name = Path(token).name.lower()
    matches = [a for a in assets if Path(str(a.get("path") or "")).name.lower() == name]
    return matches[0] if len(matches) == 1 else None


def _approval_rows(pd: Path, manifest: dict, plan: dict | None) -> list[dict]:
    used: dict[str, object] = {}
    if plan:
        for ref in plan_asset_refs(plan, pd, manifest=manifest):
            used[ref.asset_id] = ref
    rows: list[dict] = []
    for asset in manifest.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        approval = asset.get("approval") or {}
        ref = used.get(str(asset.get("asset_id") or ""))
        rows.append(
            {
                "asset_id": asset.get("asset_id"),
                "path": asset.get("path"),
                "state": approval.get("decision") or "pending",
                "reviewer": approval.get("reviewer") or "",
                "reviewed_at": approval.get("reviewed_at") or "",
                "note": approval.get("note") or "",
                "license": (asset.get("license") or {}).get("name"),
                "origin": (asset.get("origin") or {}).get("kind"),
                "scenes": list(getattr(ref, "scenes", []) or []),
                "in_plan": ref is not None,
            }
        )
    return rows


def cmd_approvals_list(args) -> int:
    pd = project_dir(args.project)
    try:
        manifest = read_manifest(pd, required=True)
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    plan = None
    try:
        plan = read_json(_resolve_plan_arg(pd))
    except (FileNotFoundError, ProjectError):
        plan = None
    try:
        manifest = sync_manifest_approvals(manifest, pd)
    except ApprovalError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    rows = _approval_rows(pd, manifest, plan)
    if getattr(args, "used_only", False):
        rows = [r for r in rows if r["in_plan"]]
    if getattr(args, "json", False):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"✔ {len(rows)} أصلًا في {pd.name}")
    for row in rows:
        mark = _STATE_MARKS.get(row["state"], "?")
        where = (" · مستخدم في مشاهد " + ",".join(row["scenes"])) if row["scenes"] else ""
        print(f"  {mark} {row['asset_id']}  {row['path']}")
        print(
            f"      {row['state']}"
            + (f" · المراجع: {row['reviewer']}" if row["reviewer"] else "")
            + f" · الترخيص: {row['license'] or '—'}"
            + f" · المصدر: {row['origin'] or '—'}"
            + where
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    print("  · " + " · ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 0


def cmd_approvals_decide(args) -> int:
    pd = project_dir(args.project)
    try:
        manifest = read_manifest(pd, required=True)
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    asset = _manifest_asset_by_token(pd, manifest, args.asset)
    if asset is None:
        print(f"✘ أصل غير موجود: {args.asset!r} — راجع: rasm approvals list {pd.name}", file=sys.stderr)
        return 2
    decision = _DECISION_WORDS.get(args.approvals_cmd, args.approvals_cmd)
    try:
        record = append_decision(
            pd,
            asset_id=str(asset.get("asset_id") or ""),
            path=str(asset.get("path") or ""),
            decision=decision,
            reviewer=args.by,
            note=getattr(args, "note", "") or "",
            license=str((asset.get("license") or {}).get("name") or ""),
            source=str((asset.get("origin") or {}).get("kind") or ""),
            origin_url=str((asset.get("origin") or {}).get("page_url") or ""),
        )
    except ApprovalError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    updated = sync_manifest_approvals(manifest, pd)
    write_manifest(pd, updated)
    print(f"✔ {decision}: {asset.get('path')} · المراجع: {record['reviewer']} · {record['reviewed_at']}")
    if getattr(args, "note", ""):
        print(f"  · ملاحظة: {args.note}")
    print("  · سجل القرارات (append-only): research/approvals.jsonl")
    return 0


def cmd_approvals_sync(args) -> int:
    pd = project_dir(args.project)
    try:
        manifest = read_manifest(pd, required=True)
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    updated = sync_manifest_approvals(manifest, pd)
    write_manifest(pd, updated)
    counts: dict[str, int] = {}
    for asset in updated.get("assets") or []:
        state = str((asset.get("approval") or {}).get("decision") or "pending")
        counts[state] = counts.get(state, 0) + 1
    print("✔ تمت مزامنة المانيفست مع سجل القرارات")
    print("  · " + " · ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 0


def cmd_approvals_import(args) -> int:
    """Pull the research asset index into the manifest (research integration)."""
    pd = project_dir(args.project)
    try:
        manifest = read_manifest(pd, required=True)
    except ProjectError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    index = pd / "research" / "assets.json"
    if not index.exists():
        print(
            "✘ لا يوجد research/assets.json — شغّل: rasm evidence "
            f"{pd.name} --download",
            file=sys.stderr,
        )
        return 2
    fresh = build_asset_entries(pd, index)
    existing = {
        str(a.get("path")): a for a in (manifest.get("assets") or []) if isinstance(a, dict)
    }
    added = 0
    touched = 0
    for entry in fresh:
        path = entry["path"]
        if path in existing:
            keep = existing[path]
            approval = keep.get("approval")
            keep.update(entry)
            if approval is not None:
                keep["approval"] = approval
            touched += 1
        else:
            existing[path] = entry
            added += 1
    manifest["assets"] = [existing[k] for k in sorted(existing)]
    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        paths = {}
    paths["assets_index"] = "research/assets.json"
    manifest["paths"] = paths
    if manifest.get("status") == "draft":
        manifest["status"] = "researched"
    manifest["updated_at"] = utc_now()
    manifest = sync_manifest_approvals(manifest, pd)
    if getattr(args, "dry_run", False):
        print(
            f"• dry-run: {added} جديد · {touched} محدَّث · الإجمالي {len(manifest['assets'])}",
        )
        return 0
    write_manifest(pd, manifest)
    print(f"✔ استيراد الأصول من البحث: {added} جديد · {touched} محدَّث · الإجمالي {len(manifest['assets'])}")
    print("  · كل الأصول تبدأ 'pending' — الاعتماد البشري شرط قبل الإنتاج")
    return 0


def cmd_approvals_gate(args) -> int:
    pd = project_dir(args.project)
    try:
        manifest = read_manifest(pd, required=True)
        plan = read_json(_resolve_plan_arg(pd))
    except (FileNotFoundError, ProjectError) as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    mode = getattr(args, "mode", "final")
    report = evaluate_gate(plan, pd, manifest=manifest, mode=mode)
    print(f"• بوابة الأصول ({mode}) · أصول مستخدمة: {len(report.used)}")
    for item in report.used:
        mark = _STATE_MARKS.get(item["state"], "?")
        print(f"  {mark} {item['asset_id']}  {item['path']}  [{item['state']}]")
    for item in report.blocking:
        print(f"  ✘ {item['reason']}: {item['path'] or item['display']} — {item['detail']}", file=sys.stderr)
    for item in report.warnings:
        print(f"  ⚠ {item['reason']}: {item['path'] or item['display']} — {item['detail']}")
    print(("✔ البوابة مفتوحة" if report.ok else "✘ البوابة مغلقة — الرندر النهائي ممنوع"))
    return 0 if report.ok else 2


def _active_plan_path(pd: Path, manifest: dict | None, explicit: str | None = None) -> Path:
    """Resolve the plan to work on **without** verifying the manifest hash.

    Commands that intentionally rewrite the plan (linking assets) must be able
    to run when the stored hash is stale — that is exactly the case they fix.
    """
    if explicit:
        raw = Path(explicit)
        candidates = [raw] if raw.is_absolute() else [
            pd / raw,
            pd / "storyboard" / raw,
            pd / "storyboard" / raw.name,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise FileNotFoundError(f"ملف الخطة غير موجود: {explicit}")
    storyboard = (manifest or {}).get("storyboard") or {}
    active = storyboard.get("active")
    if active:
        candidate = (pd / str(active)).resolve()
        if candidate.is_file():
            return candidate
    for name in ("plan_v2.json", "plan.json"):
        candidate = pd / "storyboard" / name
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("لا توجد خطة نشطة")


def cmd_project_link_assets(args) -> int:
    """Rewrite the active plan's asset paths to relative + asset_id."""
    pd = project_dir(args.project)
    try:
        manifest = read_manifest(pd, required=True)
        plan_path = _active_plan_path(pd, manifest, getattr(args, "plan", None))
        plan = read_json(plan_path)
    except (FileNotFoundError, ProjectError) as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    if not isinstance(plan, dict):
        print(f"✘ خطة غير صالحة: {plan_path}", file=sys.stderr)
        return 2
    new_plan, changes = link_plan_assets(plan, pd, manifest=manifest)
    if not changes:
        # لا مراجع لتعديلها، لكن الهاش في المانيفست يجب أن يطابق الملف الآن.
        try:
            activate_plan(pd, plan_path)
        except ProjectError as exc:
            print(f"✘ تعذّر تحديث هاش الخطة في المانيفست: {exc}", file=sys.stderr)
            return 2
        print("✔ لا توجد مسارات مطلقة — الخطة مرتبطة بالأصول بالفعل (تم تحديث الهاش)")
        return 0
    print(f"• {len(changes)} مرجع أصل في الخطة")
    for change in changes[:20]:
        print(f"   - مشهد {change['scene']} · {change['field']}: {change['from']} → {change['to']}")
    report = validate_plan(new_plan, project_dir=pd)
    if not report["ok"]:
        for error in report["errors"][:10]:
            print(f"✘ {error}", file=sys.stderr)
        print("✘ الخطة بعد الربط غير صالحة — لم تُكتب", file=sys.stderr)
        return 2
    if getattr(args, "dry_run", False):
        print("• dry-run: لم تُكتب الخطة")
        return 0
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = DATA_ROOT.parent / "backups" / "project-migrations" / f"{pd.name}-link-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plan_path, backup_dir / plan_path.name)
    shutil.copy2(project_manifest_path(pd), backup_dir / "project.json")
    write_json(plan_path, new_plan)
    try:
        activate_plan(pd, plan_path)
    except ProjectError as exc:
        print(f"✘ حُفظت الخطة لكن تعذّر تنشيطها: {exc}", file=sys.stderr)
        return 2
    manifest = read_manifest(pd, required=True) or {}
    if not plan_has_absolute_paths(new_plan):
        manifest["unresolved"] = [
            u
            for u in (manifest.get("unresolved") or [])
            if not (isinstance(u, dict) and u.get("id") == "absolute-plan-paths")
        ]
    manifest["updated_at"] = utc_now()
    write_manifest(pd, manifest)
    print(f"✔ الخطة مرتبطة: {plan_path}")
    print(f"• نسخة قبل الربط: {backup_dir}")
    return 0


def cmd_learn(args) -> int:
    from engine.memory import Lexicon, add_correction

    kind, key, value = args.kind, args.key, args.value
    if kind == "needs":
        value = [v.strip() for v in str(value).split(",") if v.strip()]
    p = add_correction(kind, key, value, note=args.note or "")
    lex = Lexicon.load()
    print(f"✔ التصحيح محفوظ: {p}")
    print(f"  {kind}({key}) = {value!r}")
    if kind == "alias":
        print(f"  أي بحث قادم لـ«{key}» سيستخدم «{lex.alias(key)}» — بلا إعادة تدريب.")
    elif kind == "type":
        print(f"  النوع القادم لـ«{key}» = {lex.type_fix(key)}")
    return 0


def cmd_validate(args) -> int:
    p = Path(args.plan)
    plan = read_json(p)
    if not plan:
        print(f"✘ تعذّر قراءة الخطة: {p}")
        return 1
    if args.project:
        pd = project_dir(args.project)
    elif p.parent.name == "storyboard":
        pd = p.parent.parent
    else:
        pd = p.parent
    report = validate_plan(plan, project_dir=pd)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["warnings"]:
        for warning in report["warnings"][:20]:
            print(f"⚠ {warning}", file=sys.stderr)
    if not report["ok"]:
        print(f"✘ خطة غير صالحة: {len(report['errors'])} خطأ", file=sys.stderr)
        return 2
    if args.strict and report["warnings"]:
        print("✘ --strict: التحذيرات تُعدّ أخطاء", file=sys.stderr)
        return 2
    print(f"✔ خطة صالحة: {report['stats']['scenes']} مشهد · {report['stats']['elements']} عنصر · {report['stats']['duration']}ث")
    return 0


def cmd_assets(args) -> int:
    """Dispatch to the Asset Studio CLI without duplicating its logic."""
    from engine.assets import studio as asset_studio

    argv = [args.assets_cmd]
    if args.assets_cmd == "generate":
        argv += [args.kind]
        if args.purpose:
            argv += ["--purpose", args.purpose]
        argv += ["--size", args.size, "--count", str(args.count), "--seed", str(args.seed),
                 "--style", args.style, "--method", args.method, "--steps", str(args.steps),
                 "--guidance", str(args.guidance)]
        if args.text_zone:
            argv += ["--text-zone", args.text_zone]
        if args.no_clean:
            argv += ["--no-clean"]
        if args.seamless:
            argv += ["--seamless"]
        if args.out:
            argv += ["--out", args.out]
        if args.prompt:
            argv += ["--prompt", args.prompt]
        if args.negative:
            argv += ["--negative", args.negative]
        if args.max_candidates:
            argv += ["--max-candidates", str(args.max_candidates)]
        if args.timeout:
            argv += ["--timeout", str(args.timeout)]
        if args.force:
            argv += ["--force"]
        if args.allow_fail:
            argv += ["--allow-fail"]
    elif args.assets_cmd == "list":
        argv += ["--style", args.style]
        if args.kind:
            argv += ["--kind", args.kind]
        if args.approved:
            argv += ["--approved", args.approved]
    elif args.assets_cmd in ("approve", "reject"):
        argv += [args.id, "--style", args.style, "--note", args.note]
    elif args.assets_cmd in ("kinds", "doctor"):
        argv += ["--style", args.style]
    elif args.assets_cmd == "brain":
        argv += [args.text, "--purpose", args.purpose]
    return asset_studio.main(argv)


def main() -> int:
    ap = argparse.ArgumentParser(prog="rasm", description="محرك راسم: فيديو وايت بورد عربي بالذكاء الاصطناعي")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("understand", help="سكريبت → تحليل بنيوي")
    p1.add_argument("script")
    p1.add_argument("--project", default="demo")
    p1.add_argument("--offline", action="store_true", help="تجاهل LLM واستخدم التحليل الاحتياطي")
    p1.set_defaults(func=cmd_understand)

    p2 = sub.add_parser("research", help="بحث حقيقي عن الحقائق والأصول")
    p2.add_argument("project")
    p2.add_argument("--max-entities", type=int, default=14)
    p2.add_argument("--no-download", action="store_true")
    p2.set_defaults(func=cmd_research)

    pe = sub.add_parser("evidence", help="بحث مسنّد: متطلبات + مصادر + مرشحات + أدلة")
    pe.add_argument("project")
    pe.add_argument("--script", help="ملف سكريبت (اختياري)")
    pe.add_argument("--srt", help="ملف SRT مع timestamps")
    pe.add_argument("--source-url", action="append", default=[], help="رابط مصدر كامل (قابل للتكرار)")
    pe.add_argument("--doc", action="append", default=[], help="مستند محلي (قابل للتكرار)")
    pe.add_argument("--language", default=None, help="ar أو en")
    pe.add_argument("--download", action="store_true", help="تنزيل المرشحات المسموح بها")
    pe.add_argument("--no-resume", action="store_true")
    pe.add_argument("--max-seconds", type=float, default=300.0)
    pe.add_argument("--max-requests", type=int, default=40)
    pe.add_argument("--max-pages", type=int, default=25)
    pe.add_argument("--max-downloads", type=int, default=12)
    pe.add_argument("--max-download-bytes", type=int, default=25000000)
    pe.add_argument("--max-depth", type=int, default=2)
    pe.add_argument("--max-llm-calls", type=int, default=12)
    pe.add_argument("--max-llm-tokens", type=int, default=1200)
    pe.add_argument("--concurrency", type=int, default=2)
    pe.set_defaults(func=cmd_evidence)

    pl = sub.add_parser("llm-status", help="فحص Qwen 4B (auth/model/backend)")
    pl.set_defaults(func=cmd_llm_status)

    p3 = sub.add_parser("strokes", help="مساراً: SVG/صورة/نص → معاينة رسم")
    p3.add_argument("path", nargs="?")
    p3.add_argument("--text")
    p3.add_argument("--font")
    p3.add_argument("--size", type=float, default=110)
    p3.add_argument("--mode", default="skeleton", choices=["skeleton", "outline"])
    p3.add_argument("--out")
    p3.add_argument("--strip", action="store_true")
    p3.set_defaults(func=cmd_strokes)

    p4 = sub.add_parser("icons", help="بحث في مكتبة الأيقونات المحلية")
    p4.add_argument("keywords", nargs="+")
    p4.add_argument("--limit", type=int, default=8)
    p4.set_defaults(func=cmd_icons)

    p5 = sub.add_parser("plan", help="بناء الستوري بورد من التحليل والبحث")
    p5.add_argument("project")
    p5.add_argument("--max-scenes", type=int, default=None)
    p5.add_argument("--fps", default=None, help="معدل الإطارات (افتراضي: مانيفست المشروع أو 24)")
    p5.set_defaults(func=cmd_plan)

    pj = sub.add_parser("project", help="مانيفست المشروع: init / validate / migrate")
    pjsub = pj.add_subparsers(dest="project_cmd", required=True)
    pji = pjsub.add_parser("init", help="إنشاء project.json من مشروع موجود")
    pji.add_argument("project")
    pji.add_argument("--plan", default=None, help="الخطة النشطة (مثال: storyboard/plan_v2.json)")
    pji.add_argument("--title", default=None)
    pji.add_argument("--language", default=None)
    pji.add_argument("--force", action="store_true")
    pji.add_argument("--dry-run", action="store_true")
    pji.set_defaults(func=cmd_project_init)

    pjv = pjsub.add_parser("validate", help="فحص المانيفست والمسارات والهاشات والخطة")
    pjv.add_argument("project")
    pjv.set_defaults(func=cmd_project_validate)

    pjm = pjsub.add_parser("migrate", help="ترحيل آمن إلى project.json (dry-run افتراضيًا)")
    pjm.add_argument("project")
    pjm.add_argument("--plan", default=None, help="الخطة النشطة (افتراضي: plan_v2 إن وجدت)")
    pjm.add_argument("--title", default=None)
    pjm.add_argument("--language", default=None)
    pjm.add_argument("--apply", action="store_true", help="كتابة المانيفست (بدونها dry-run)")
    pjm.add_argument("--force", action="store_true", help="تحديث مانيفست موجود مختلف")

    # ---- المرحلة 3: اعتماد الأصول (بوابة الإنتاج) ----
    pap = sub.add_parser("approvals", help="اعتماد أصول المشروع (سجل + بوابة إنتاج)")
    papsub = pap.add_subparsers(dest="approvals_cmd", required=True)

    papl = papsub.add_parser("list", help="عرض الأصول وحالة الاعتماد")
    papl.add_argument("project")
    papl.add_argument("--used-only", action="store_true", help="الأصول المستخدمة في الخطة فقط")
    papl.add_argument("--json", action="store_true")
    papl.set_defaults(func=cmd_approvals_list)

    for _word, _help in (
        ("approve", "اعتماد أصل بعد مراجعته"),
        ("reject", "رفض أصل"),
        ("defer", "تأجيل قرار أصل"),
    ):
        pad = papsub.add_parser(_word, help=_help)
        pad.add_argument("project")
        pad.add_argument("--asset", required=True, help="asset_id أو مسار الأصل داخل المشروع")
        pad.add_argument("--by", required=True, help="اسم المراجع البشري")
        pad.add_argument("--note", default="", help="ملاحظة القرار")
        pad.set_defaults(func=cmd_approvals_decide)

    paps = papsub.add_parser("sync", help="مزامنة المانيفست مع سجل القرارات")
    paps.add_argument("project")
    paps.set_defaults(func=cmd_approvals_sync)

    papi = papsub.add_parser("import", help="استيراد أصول البحث (research/assets.json) إلى المانيفست")
    papi.add_argument("project")
    papi.add_argument("--dry-run", action="store_true")
    papi.set_defaults(func=cmd_approvals_import)

    pag = papsub.add_parser("gate", help="فحص بوابة الأصول قبل الإنتاج")
    pag.add_argument("project")
    pag.add_argument("--mode", choices=["final", "preview"], default="final")
    pag.set_defaults(func=cmd_approvals_gate)

    pjl = pjsub.add_parser(
        "link-assets",
        help="ربط الخطة بالأصول: مسارات نسبية + asset_id (مع نسخة قبل الكتابة)",
    )
    pjl.add_argument("project")
    pjl.add_argument("--plan", default=None, help="خطة بديلة (افتراضي: الخطة النشطة)")
    pjl.add_argument("--dry-run", action="store_true")
    pjl.set_defaults(func=cmd_project_link_assets)
    pjm.set_defaults(func=cmd_project_migrate)

    pv = sub.add_parser("validate", help="فحص خطة JSON قبل الرندر")
    pv.add_argument("plan")
    pv.add_argument("--project", default=None, help="مجلد المشروع لحل مسارات الأصول النسبية")
    pv.add_argument("--strict", action="store_true", help="التحذيرات تُعدّ أخطاء")
    pv.set_defaults(func=cmd_validate)

    p6 = sub.add_parser("render", help="رندر الفيديو من الخطة")
    p6.add_argument("project")
    p6.add_argument("--out")
    p6.add_argument("--size", default="1280x720")
    p6.add_argument("--fps", default=None, help="معدل الإطارات (افتراضي: الخطة النشطة؛ لا يُسمح بالتعارض)")
    p6.add_argument("--crf", type=int, default=19)
    p6.add_argument("--scenes", help="مثل 1-3 أو 2")
    p6.add_argument("--max-seconds", type=float, default=None)
    p6.add_argument("--plan", help="ملف خطة بديل داخل مجلد storyboard (مثال: plan_v2.json)")
    p6.add_argument("--no-sfx", dest="sfx", action="store_false", help="تعطيل مؤثرات القلم (مفعّلة افتراضيًا)")
    p6.add_argument("--sfx-preset", choices=["paper", "subtle", "bold"], default="paper", help="شدة المؤثرات")
    p6.add_argument("--audio", help="ملف تعليق صوتي (وإلا يُستخدم صوت المشروع تلقائيًا)")
    p6.add_argument("--skip-validate", action="store_true", help="تجاوز فحص الخطة (للملفات القديمة فقط)")
    p6.add_argument(
        "--preview",
        action="store_true",
        help="معاينة: يسمح بأصول غير معتمدة (مع تحذير) — الإنتاج يتطلب اعتمادًا",
    )
    p6.set_defaults(func=cmd_render)

    p8 = sub.add_parser("audio", help="استيراد تعليق صوتي + فحص دقيق + محاذاة تقديرية صريحة")
    p8.add_argument("project")
    p8.add_argument("--file", required=True, help="ملف الصوت الأصلي (لا يُعدَّل)")
    p8.add_argument("--no-copy", action="store_true", help="مرجع مباشر بدل نسخة داخل المشروع")
    p8.add_argument("--note", default="", help="ملاحظة (قارئ الصوت/الجلسة)")
    p8.set_defaults(func=cmd_audio)

    p7 = sub.add_parser("learn", help="تصحيح دائم يتعلمه المحرك (اسم/نوع/احتياجات)")
    p7.add_argument("kind", choices=["alias", "type", "needs"], help="alias: اسم شائع→مرجعي · type: تصحيح النوع · needs: احتياجات بصرية")
    p7.add_argument("key", help="الاسم كما يظهر في السكريبت")
    p7.add_argument("value", help="القيمة الجديدة (للاحتياجات: فصل بفواصل)")
    p7.add_argument("--note", default="", help="سبب التصحيح (للتوثيق)")
    p7.set_defaults(func=cmd_learn)

    p9 = sub.add_parser("assets", help="توليد ومراجعة أصول ورقية/كولاج بالاستايل المقفول")
    asub = p9.add_subparsers(dest="assets_cmd", required=True)
    ag = asub.add_parser("generate", help="توليد أصل جديد (إجرائي أو SD1.5)")
    ag.add_argument("kind")
    ag.add_argument("--purpose", choices=["background", "card", "scrap", "overlay"], default=None)
    ag.add_argument("--size", default="2560x1440")
    ag.add_argument("--count", type=int, default=3)
    ag.add_argument("--seed", type=int, default=42)
    ag.add_argument("--style", default="paper_ink_v1")
    ag.add_argument("--method", choices=["auto", "procedural", "sd15"], default="auto")
    ag.add_argument("--text-zone", default=None)
    ag.add_argument("--no-clean", action="store_true")
    ag.add_argument("--seamless", action="store_true")
    ag.add_argument("--out", default=None)
    ag.add_argument("--prompt", default=None)
    ag.add_argument("--negative", default=None)
    ag.add_argument("--steps", type=int, default=20)
    ag.add_argument("--guidance", type=float, default=7.0)
    ag.add_argument("--max-candidates", type=int, default=None)
    ag.add_argument("--timeout", type=int, default=None)
    ag.add_argument("--force", action="store_true")
    ag.add_argument("--allow-fail", action="store_true")
    ag.set_defaults(func=cmd_assets)

    ak = asub.add_parser("kinds", help="عرض أنواع الأصول")
    ak.add_argument("--style", default="paper_ink_v1")
    ak.set_defaults(func=cmd_assets)

    al = asub.add_parser("list", help="عرض الأصول المولدة")
    al.add_argument("--kind", default=None)
    al.add_argument("--approved", choices=["yes", "no"], default=None)
    al.add_argument("--style", default="paper_ink_v1")
    al.set_defaults(func=cmd_assets)

    aa = asub.add_parser("approve", help="اعتماد أصل")
    aa.add_argument("id")
    aa.add_argument("--note", default="")
    aa.add_argument("--style", default="paper_ink_v1")
    aa.set_defaults(func=cmd_assets)

    ar = asub.add_parser("reject", help="رفض أصل")
    ar.add_argument("id")
    ar.add_argument("--note", default="")
    ar.add_argument("--style", default="paper_ink_v1")
    ar.set_defaults(func=cmd_assets)

    ad = asub.add_parser("doctor", help="فحص الاستوديو وSD1.5")
    ad.add_argument("--style", default="paper_ink_v1")
    ad.set_defaults(func=cmd_assets)

    ab = asub.add_parser("brain", help="اقتراح نوع الأصل من وصف المشهد")
    ab.add_argument("text")
    ab.add_argument("--purpose", choices=["background", "card", "scrap", "overlay"], default="background")
    ab.set_defaults(func=cmd_assets)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
