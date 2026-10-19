# -*- coding: utf-8 -*-
"""مقاطع عرض للقوالب السينمائية الثلاثة — Premium Whiteboard / Documentary Collage / Timeline.

كل مقطع: خطة مبنية برمجيًا (بلا مشروع وسيط)، رندر 1280×720@24، ثم مؤثرات قلم
حقيقية (PDSounds، ملكية عامة) مدمجة في نفس الملف.
المخرجات: qa/phase31_templates/*.mp4
تشغيل:  .venv\\Scripts\\python.exe tools\\make_templates_demo.py [اسم_القالب ...]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from engine.render.director import Director  # noqa: E402
from engine.audio.sfx import build_track, mux_into  # noqa: E402

OUT = ROOT / "qa" / "phase31_templates"
IMG_SOMME = ROOT / "projects" / "ww1" / "assets" / "event-معركة-السوم" / "c75888b731eb.jpg"
IMG_VERSAILLES = ROOT / "projects" / "ww1" / "assets" / "event-معاهدة-فرساي" / "6aee608a669e.jpg"

CANVAS = (2560, 1440)
OUT_SIZE = (1280, 720)
FPS = 24


def plan(scenes: list[dict]) -> dict:
    return {"project": "templates-demo", "lang": "ar", "canvas": list(CANVAS), "fps": FPS,
            "scenes": [{**s, "duration": 0} for s in scenes]}


# ---------- 1) لوحة بيضاء بريميوم ----------
PREMIUM = plan([
    {"id": 1, "start_pause": 0.4, "elements": [
        {"type": "highlight", "rect": [170, 300, 2220, 300], "color": "#F3D57C", "speed": 2.1, "gap": 0.12, "events": False},
        {"type": "text", "font": "arefruqaa", "size": 250, "text": "قوالب احترافية", "rtl": True, "mode": "skeleton",
         "rect": [200, 285, 2160, 350], "color": "#211E1A", "gap": 0.18},
        {"type": "underline", "rect": [200, 285, 2160, 350], "double": True, "color": "#8C2F1F", "brush": 6.0,
         "offset": 14, "gap": 0.25},
        {"type": "text", "font": "amiri", "size": 108, "text": "لوحة بيضاء سينمائية بخط عربي متصل", "rtl": True,
         "mode": "skeleton", "rect": [260, 800, 2060, 150], "color": "#211E1A", "gap": 0.3},
        {"type": "flourish", "rect": [260, 800, 2060, 150], "color": "#8C2F1F", "gap": 0.2},
    ]},
    {"id": 2, "start_pause": 0.4, "elements": [
        {"type": "paper_card", "rect": [190, 420, 1010, 700], "style": "photo", "tilt": -1.1, "seed": 4, "gap": 0.12},
        {"type": "image", "asset": str(IMG_SOMME), "rect": [190, 420, 1010, 700], "trace_size": 720, "gap": 0.35},
        {"type": "torn_strip", "rect": [1330, 570, 1010, 210], "seed": 9, "tilt": 0.5, "gap": 0.1},
        {"type": "text", "font": "amiri", "size": 92, "text": "صورة حقيقية على بطاقة ورقية", "rtl": True,
         "mode": "skeleton", "rect": [1350, 590, 970, 170], "color": "#211E1A", "gap": 0.2},
        {"type": "arrow", "from": [1380, 560], "to": [1230, 800], "curve": 0.28, "brush": 5.0,
         "color": "#8C2F1F", "speed": 1.3, "gap": 0.2},
    ]},
])

# ---------- 2) كولاج وثائقي ورقي ----------
COLLAGE = plan([
    {"id": 1, "start_pause": 0.4, "elements": [
        {"type": "torn_strip", "rect": [150, 170, 2260, 280], "seed": 3, "tilt": 0.0, "gap": 0.12},
        {"type": "text", "font": "arefruqaa", "size": 190, "text": "كولاج وثائقي", "rtl": True, "mode": "skeleton",
         "rect": [400, 195, 1760, 230], "color": "#211E1A", "gap": 0.2},
        {"type": "underline", "rect": [400, 195, 1760, 230], "double": False, "color": "#8C2F1F", "brush": 5.5,
         "offset": 10, "gap": 0.3},
        {"type": "paper_card", "rect": [180, 620, 900, 620], "style": "photo", "tilt": -2.2, "seed": 6, "gap": 0.14},
        {"type": "image", "asset": str(IMG_VERSAILLES), "rect": [180, 620, 900, 620], "trace_size": 640, "gap": 0.3},
        {"type": "paper_card", "rect": [1220, 680, 780, 540], "style": "photo", "tilt": 1.8, "seed": 8, "gap": 0.14},
        {"type": "image", "asset": str(IMG_SOMME), "rect": [1220, 680, 780, 540], "trace_size": 600, "gap": 0.3},
        {"type": "torn_strip", "rect": [780, 560, 700, 160], "seed": 11, "tilt": -1.0, "gap": 0.1},
        {"type": "text", "font": "amiri", "size": 76, "text": "أرشيف الحرب", "rtl": True, "mode": "skeleton",
         "rect": [830, 585, 600, 120], "color": "#8C2F1F", "gap": 0.2},
    ]},
    {"id": 2, "start_pause": 0.4, "elements": [
        {"type": "torn_strip", "rect": [330, 560, 1900, 300], "seed": 13, "tilt": 0.4, "gap": 0.12},
        {"type": "text", "font": "amiri", "size": 112, "text": "قصاصات ورقية وأشرطة لاصقة وظلال ناعمة", "rtl": True,
         "mode": "skeleton", "rect": [380, 600, 1800, 220], "color": "#211E1A", "gap": 0.25},
        {"type": "flourish", "rect": [380, 600, 1800, 220], "color": "#8C2F1F", "gap": 0.2},
    ]},
])

# ---------- 3) خط زمني وقصة بيانات ----------
TIMELINE = plan([
    {"id": 1, "start_pause": 0.4, "elements": [
        {"type": "text", "font": "arefruqaa", "size": 185, "text": "خط زمني للحرب", "rtl": True, "mode": "skeleton",
         "rect": [160, 130, 1400, 240], "color": "#211E1A", "gap": 0.2},
        {"type": "underline", "rect": [160, 130, 1400, 240], "double": False, "color": "#8C2F1F", "brush": 5.5,
         "offset": 10, "gap": 0.35},
        {"type": "timeline", "rect": [150, 560, 2260, 760], "font": "arefruqaa", "size": 72, "rtl": True,
         "seed": 41, "brush": 5.0, "color": "#211E1A", "speed": 1.5, "gap": 0.3,
         "events": [
             {"label": "1914", "sub": "اندلاع الحرب"},
             {"label": "1916", "sub": "السوم وفردان"},
             {"label": "1917", "sub": "دخول أمريكا"},
             {"label": "1918", "sub": "نهاية الحرب"},
             {"label": "1919", "sub": "معاهدة فرساي"},
         ]},
    ]},
    {"id": 2, "start_pause": 0.4, "elements": [
        {"type": "text", "font": "amiri", "size": 108, "text": "قالب بيانات (عرض توضيحي)", "rtl": True,
         "mode": "skeleton", "rect": [180, 140, 1600, 170], "color": "#8C2F1F", "gap": 0.25},
        {"type": "bars", "rect": [180, 430, 2200, 720], "font": "arefruqaa", "size": 64, "seed": 51, "brush": 5.0,
         "color": "#211E1A", "speed": 1.3, "gap": 0.25,
         "values": [40, 65, 85], "labels": ["1914", "1916", "1918"]},
        {"type": "text", "font": "amiri", "size": 78, "text": "أرقام المثال توضيحية وليست بيانات تاريخية", "rtl": True,
         "mode": "skeleton", "rect": [300, 1240, 1960, 120], "color": "#6B6459", "gap": 0.2},
    ]},
])

PLANS = {
    "premium_whiteboard": PREMIUM,
    "documentary_collage": COLLAGE,
    "timeline_data_story": TIMELINE,
}


def measure_plan(pl: dict) -> list[float]:
    """زمن طبيعي لكل مشهد (بلا ضغط) — نضبط المدة عليه + هامش."""
    d = Director(pl, canvas=CANVAS, out_size=OUT_SIZE, fps=FPS)
    durs = []
    for sc in pl["scenes"]:
        items = d._prepare_scene(sc)
        nat = max((it["start"] + it["dur"] for it in items), default=0.0)
        durs.append(round(nat + 1.0, 3))
    return durs


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    names = argv or list(PLANS)
    for name in names:
        pl = PLANS[name]
        durs = measure_plan(pl)
        for sc, dur in zip(pl["scenes"], durs):
            sc["duration"] = dur
        out = OUT / f"{name}.mp4"
        t0 = time.time()
        res = Director(pl, canvas=CANVAS, out_size=OUT_SIZE, fps=FPS).render(out)
        sfx = build_track(res["sfx"], out.with_suffix(".sfx.wav"), preset="paper", duration=res["seconds"])
        mux = mux_into(out, out.with_suffix(".sfx.wav"), out)
        print(f"[{name}] {res['frames']} إطار · {res['seconds']}ث · رندر {res['render_seconds']}ث · "
              f"مؤثرات: {sfx['scratches']} رسمة/{sfx['taps']} نقرة · حقيقي={sfx['real_recordings']} · {mux['mode']} · "
              f"مدة المشاهد {durs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
