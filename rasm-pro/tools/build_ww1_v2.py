# -*- coding: utf-8 -*-
"""يبني projects/ww1/storyboard/plan_v2.json — النسخة السينمائية المحسّنة (Phase 3.1).

القواعد:
- plan.json (v1) يبقى كما هو — الأصل قابل للاسترجاع.
- المحتوى النصي من الخطة الأصلية (نفس صياغة الفيديو) بلا اختلاق.
- القوالب: مشاهد 1/5 بريميوم (تظليل+تسطير+زخرفة)، 2/4 كولاج ورق (بطاقات+قصاصات)،
  3 خط زمني (قصص بيانات).
- المدد تُقاس من الزمن الطبيعي للرسم (HandTimeline بلا ضغط) + هامش 1.0ث،
  فلا يبدو الرسم متعجلًا.
تشغيل: .venv\\Scripts\\python.exe tools\\build_ww1_v2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from engine.render.director import Director  # noqa: E402

PD = ROOT / "projects" / "ww1"
IMG_SOMME = str(PD / "assets" / "event-معركة-السوم" / "c75888b731eb.jpg")
IMG_SOMME2 = str(PD / "assets" / "event-معركة-السوم" / "a21b49758ec5.jpg")
IMG_VERSAILLES = str(PD / "assets" / "event-معاهدة-فرساي" / "6aee608a669e.jpg")

CANVAS = [2560, 1440]
FPS = 24
# معامل الإيقاع: الزمن الطبيعي للرسم × 0.72 (كتابة غير متعجلة، والفيلم لا يطول).
# مكتوب صراحةً في التقرير — لا ضغط خفي.
PACING = 0.72

PLAN = {
    "project": "266148524df9ad38",
    "lang": "ar",
    "canvas": CANVAS,
    "fps": FPS,
    "note": "Phase 3.1 v2 — نسخة القوالب السينمائية. v1 محفوظ في plan.json.",
    "scenes": [
        {
            "id": 1,
            "narration": None,
            "needs": ["portrait", "event"],
            "assets_used": [],
            "elements": [
                {"type": "highlight", "rect": [150, 300, 2240, 340], "color": "#F3D57C",
                 "speed": 2.2, "events": False, "gap": 0.14},
                {"type": "text", "text": "في صيف عام 1914،\nاشتعلت الحرب…", "font": "arefruqaa", "size": 260,
                 "rect": [130, 285, 2300, 380], "mode": "skeleton", "rtl": True, "color": "#211E1A", "gap": 0.2},
                {"type": "underline", "rect": [130, 285, 2300, 380], "double": True, "color": "#8C2F1F",
                 "brush": 6.5, "offset": 16, "gap": 0.3},
                {"type": "text",
                 "text": "العالمية الأولى بعد اغتيال\nالأرشيدوق فرانز فرديناند في سراييفو.\nكانت الإمبراطورية الألمانية والنمسا والمجر\nفي مواجهة بريطانيا وفرنسا وروسيا.",
                 "font": "amiri", "size": 96, "rect": [190, 920, 2180, 480], "mode": "skeleton", "rtl": True,
                 "color": "#8C2F1F", "gap": 0.35},
                {"type": "flourish", "rect": [190, 920, 2180, 480], "color": "#8C2F1F", "gap": 0.2},
            ],
        },
        {
            "id": 2,
            "narration": None,
            "needs": ["event"],
            "assets_used": [IMG_SOMME, IMG_SOMME2],
            "elements": [
                {"type": "torn_strip", "rect": [1420, 130, 1030, 250], "seed": 21, "tilt": -0.6, "gap": 0.12},
                {"type": "text", "text": "معركة السوم", "font": "cairo", "size": 92, "rect": [1450, 150, 980, 200],
                 "mode": "skeleton", "rtl": True, "color": "#8C2F1F", "gap": 0.25},
                {"type": "paper_card", "rect": [110, 330, 1300, 880], "style": "photo", "tilt": -1.3, "seed": 4, "gap": 0.12},
                {"type": "image", "asset": IMG_SOMME, "rect": [110, 330, 1300, 880], "trace_size": 900, "gap": 0.35},
                {"type": "paper_card", "rect": [1500, 470, 760, 560], "style": "photo", "tilt": 1.9, "seed": 9, "gap": 0.12},
                {"type": "image", "asset": IMG_SOMME2, "rect": [1500, 470, 760, 560], "trace_size": 520, "gap": 0.3},
                {"type": "text", "text": "حفر الجنود الخنادق على الجبهة\nالغربية في معركة السوم وفردان.",
                 "font": "amiri", "size": 92, "rect": [1470, 1080, 940, 280], "mode": "skeleton", "rtl": True,
                 "color": "#211E1A", "gap": 0.3},
            ],
        },
        {
            "id": 3,
            "narration": None,
            "needs": ["portrait", "event", "map"],
            "assets_used": [],
            "elements": [
                {"type": "text",
                 "text": "في عام 1917، دخلت\nالولايات المتحدة الحرب\nإلى جانب الحلفاء بعد رسالة زيمرمان.",
                 "font": "arefruqaa", "size": 185, "rect": [130, 130, 2300, 560], "mode": "skeleton", "rtl": True,
                 "color": "#211E1A", "gap": 0.2},
                {"type": "underline", "rect": [130, 130, 2300, 560], "double": True, "color": "#8C2F1F",
                 "brush": 6.0, "offset": 14, "gap": 0.35},
                {"type": "timeline", "rect": [150, 780, 2260, 580], "font": "arefruqaa", "size": 74, "rtl": True,
                 "seed": 41, "brush": 5.0, "color": "#211E1A", "speed": 1.5, "gap": 0.3, "events": [
                     {"label": "1914", "sub": "اندلاع الحرب"},
                     {"label": "1916", "sub": "السوم وفردان"},
                     {"label": "1917", "sub": "دخول أمريكا"},
                     {"label": "1918", "sub": "نهاية الحرب"},
                     {"label": "1919", "sub": "معاهدة فرساي"},
                 ]},
            ],
        },
        {
            "id": 4,
            "narration": None,
            "needs": ["event", "chart"],
            "assets_used": [IMG_VERSAILLES],
            "elements": [
                {"type": "torn_strip", "rect": [1420, 130, 1030, 250], "seed": 23, "tilt": 0.5, "gap": 0.12},
                {"type": "text", "text": "معاهدة فرساي", "font": "cairo", "size": 92, "rect": [1450, 150, 980, 200],
                 "mode": "skeleton", "rtl": True, "color": "#8C2F1F", "gap": 0.25},
                {"type": "paper_card", "rect": [110, 330, 1300, 880], "style": "photo", "tilt": -1.2, "seed": 5, "gap": 0.12},
                {"type": "image", "asset": IMG_VERSAILLES, "rect": [110, 330, 1300, 880], "trace_size": 900, "gap": 0.35},
                {"type": "text", "text": "وقّعت ألمانيا معاهدة فرساي\nفي يونيو 1919، وفرضت عليها\nتعويضات ضخمة.",
                 "font": "amiri", "size": 92, "rect": [1470, 470, 940, 480], "mode": "skeleton", "rtl": True,
                 "color": "#211E1A", "gap": 0.32},
                {"type": "torn_strip", "rect": [1490, 1090, 900, 300], "seed": 25, "tilt": -0.4, "gap": 0.1},
                {"type": "highlight", "rect": [1530, 1150, 820, 190], "color": "#F3D57C", "speed": 1.8,
                 "events": False, "gap": 0.1},
                {"type": "text", "text": "نحو 17 مليون قتيل", "font": "arefruqaa", "size": 150,
                 "rect": [1530, 1150, 820, 190], "mode": "skeleton", "rtl": True, "color": "#8C2F1F", "gap": 0.25},
            ],
        },
        {
            "id": 5,
            "narration": None,
            "needs": ["portrait", "event", "map"],
            "assets_used": [],
            "elements": [
                {"type": "highlight", "rect": [150, 425, 2240, 420], "color": "#F3D57C", "speed": 2.2,
                 "events": False, "gap": 0.14},
                {"type": "text", "text": "رسمت هذه الحرب خريطة\nالشرق الأوسط من جديد، وأسست\nعصبة الأمم.",
                 "font": "arefruqaa", "size": 190, "rect": [130, 420, 2300, 430], "mode": "skeleton", "rtl": True,
                 "color": "#211E1A", "gap": 0.2},
                {"type": "underline", "rect": [130, 420, 2300, 430], "double": True, "color": "#8C2F1F",
                 "brush": 6.5, "offset": 16, "gap": 0.3},
                {"type": "text", "text": "هكذا انتهى عصر الإمبراطوريات\nوبدأ القرن العشرون بوجه جديد.",
                 "font": "amiri", "size": 104, "rect": [190, 950, 2180, 340], "mode": "skeleton", "rtl": True,
                 "color": "#8C2F1F", "gap": 0.32},
                {"type": "flourish", "rect": [190, 950, 2180, 340], "color": "#8C2F1F", "gap": 0.2},
            ],
        },
    ],
}


def main() -> int:
    plan = json.loads(json.dumps(PLAN))
    d = Director(plan, canvas=tuple(CANVAS), out_size=(1280, 720), fps=FPS)
    total = 0.0
    for sc in plan["scenes"]:
        sc["duration"] = 0
        items = d._prepare_scene(sc)
        nat = max((it["start"] + it["dur"] for it in items), default=0.0)
        sc["duration"] = round(nat * PACING, 2)
        total += sc["duration"]
        kinds = ", ".join(e["type"] for e in sc["elements"])
        print(f"مشهد {sc['id']}: طبيعي {nat:.2f}ث → مدة {sc['duration']}ث (×{PACING}) · عناصر: {kinds}")
    plan["stats"] = {"scenes": len(plan["scenes"]),
                     "elements": sum(len(s["elements"]) for s in plan["scenes"]),
                     "estimated_duration": round(total, 1)}
    out = PD / "storyboard" / "plan_v2.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✔ كُتب: {out} · المجموع ≈ {plan['stats']['estimated_duration']}ث")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
