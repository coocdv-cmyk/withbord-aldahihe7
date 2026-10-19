#!/usr/bin/env python
"""rasm — واجهة سطر الأوامر للمحرك (فهم → بحث → مسارات → معاينة)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.core.log import get_logger  # noqa: E402
from engine.core.paths import project_dir  # noqa: E402
from engine.core.util import read_json  # noqa: E402
from engine.render import Director  # noqa: E402
from engine.stages import plan as plan_stage  # noqa: E402
from engine.stages import research as research_stage  # noqa: E402
from engine.stages import understanding as understanding_stage  # noqa: E402
from engine.strokes import (  # noqa: E402
    find_font,
    raster_to_strokes,
    render_preview,
    render_strip,
    scan_svg,
    text_to_strokes,
)

log = get_logger("cli")


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


def cmd_strokes(args) -> int:
    out = Path(args.out) if args.out else ROOT / "cache" / "preview.png"
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
    plan = plan_stage.build_plan(graph, research, project_dir=pd, max_scenes=args.max_scenes)
    out = plan_stage.save_plan(plan, pd)
    print(f"✔ الخطة محفوظة: {out}")
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
    plan_file = getattr(args, "plan", None) or "plan.json"
    plan = read_json(pd / "storyboard" / plan_file)
    if not plan:
        graph = read_json(pd / "script" / "scriptgraph.json")
        if not graph:
            print("✘ لا يوجد تحليل — شغّل: rasm understand ثم rasm plan")
            return 1
        research = read_json(pd / "research" / "research.json", default={}) or {}
        plan = plan_stage.build_plan(graph, research, project_dir=pd)
        plan_stage.save_plan(plan, pd)
        print("• تم بناء الخطة تلقائيًا")

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
    elif plan_audio.get("file") and Path(plan_audio["file"]).exists():
        audio_file = plan_audio["file"]
    else:
        from engine.audio import load_narration

        nar = load_narration(pd)
        if nar:
            audio_file = nar.get("path")
    if audio_file:
        print(f"• سرد صوتي: {Path(audio_file).name}")

    director = Director(plan, canvas=canvas, out_size=size, fps=args.fps, crf=args.crf)
    res = director.render(out, audio=audio_file, max_seconds=args.max_seconds, scene_range=scene_range)
    print(f"✔ الفيديو: {res['out']}")
    print(f"  {res['frames']} إطار · {res['seconds']}ث · زمن الرندر {res['render_seconds']}ث")

    # مؤثرات صوتية واقعية من أحداث القلم (تُدمج في نفس ملف الفيديو)
    sfx_muxed = False
    if getattr(args, "sfx", True) and res.get("sfx") and Path(res["sfx"]).exists():
        try:
            from engine.audio.sfx import build_track, mux_into

            wav = Path(str(out)).with_suffix(".sfx.wav")
            info = build_track(res["sfx"], wav, preset=getattr(args, "sfx_preset", "paper"),
                               duration=res["seconds"])
            mux = mux_into(out, wav, out, narration=None)
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

    exp_dur = plan_audio.get("duration_sec")
    if audio_file and exp_dur is None:
        from engine.audio import load_narration

        nar = load_narration(pd) or {}
        exp_dur = nar.get("duration_sec")
    report = validate_video(
        out,
        expect_size=size,
        expect_fps=args.fps,
        expect_audio=bool(audio_file) or sfx_muxed,
        expect_duration_sec=exp_dur if audio_file else None,
        tolerance_frames=2 if audio_file else 1,
    )
    print(("✔" if report["ok"] else "✘") + f" تحقق FFprobe: {report['path']}")
    for c in report["checks"]:
        print(f"   {'✔' if c['ok'] else '✘'} {c['check']}: {c['detail']}")
    return 0 if report["ok"] else 2


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
    p5.set_defaults(func=cmd_plan)

    p6 = sub.add_parser("render", help="رندر الفيديو من الخطة")
    p6.add_argument("project")
    p6.add_argument("--out")
    p6.add_argument("--size", default="1280x720")
    p6.add_argument("--fps", type=int, default=30)
    p6.add_argument("--crf", type=int, default=19)
    p6.add_argument("--scenes", help="مثل 1-3 أو 2")
    p6.add_argument("--max-seconds", type=float, default=None)
    p6.add_argument("--plan", help="ملف خطة بديل داخل مجلد storyboard (مثال: plan_v2.json)")
    p6.add_argument("--no-sfx", dest="sfx", action="store_false", help="تعطيل مؤثرات القلم (مفعّلة افتراضيًا)")
    p6.add_argument("--sfx-preset", choices=["paper", "subtle", "bold"], default="paper", help="شدة المؤثرات")
    p6.add_argument("--audio", help="ملف تعليق صوتي (وإلا يُستخدم صوت المشروع تلقائيًا)")
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

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
