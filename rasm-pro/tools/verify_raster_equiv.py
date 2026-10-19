# -*- coding: utf-8 -*-
"""تكافؤ تتبّع الصور: المسارات الجديدة (بعد تحسين mask_path) ضد كاش القرص
المحسوب بالنسخة القديمة — على صور الفيلم الحقيقية نفسها.

تشغيل: .venv\\Scripts\\python.exe tools\\verify_raster_equiv.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from engine.render.director import _sig  # noqa: E402
from engine.strokes import raster_to_strokes  # noqa: E402
from engine.strokes.model import StrokeDoc, stroke_cache_path  # noqa: E402

plan = json.loads((ROOT / "projects" / "ww1" / "storyboard" / "plan_v2.json").read_text(encoding="utf-8"))
els = [el for sc in plan["scenes"] for el in sc.get("elements", []) if el.get("type") == "image"]
print(f"صور الخطة: {len(els)}")

all_ok = True
for el in els:
    path = el["asset"]
    size = int(el.get("trace_size", 900))
    rtl = bool(el.get("rtl", False))
    key = f"raster|{path}|{_sig(path)}|{size}|{rtl}"
    p = stroke_cache_path(key)
    if not p.exists():
        print(f"⚠ لا كاش للمفتاح: {Path(path).name} (size={size}) — لا مقارنة")
        all_ok = False
        continue
    old = StrokeDoc.load(p)
    img = Image.open(path).convert("RGB")
    new = raster_to_strokes(np.asarray(img), max_size=size, rtl=rtl)
    name = Path(path).name
    if len(old.strokes) != len(new.strokes):
        print(f"✘ {name}: عدد المسارات مختلف {len(old.strokes)} != {len(new.strokes)}")
        all_ok = False
        continue
    bad = 0
    for i, (a, b) in enumerate(zip(old.strokes, new.strokes)):
        if a.points != b.points:
            bad += 1
            if bad == 1:
                print(f"✘ {name}: مسار {i} نقاطه مختلفة ({len(a.points)} != {len(b.points)})")
        elif a.lengths != b.lengths or a.brush != b.brush or a.jumps != b.jumps:
            bad += 1
            if bad == 1:
                print(f"✘ {name}: مسار {i} بياناته مختلفة (أطوال/فرشاة/قفزات)")
        elif a.kind != b.kind or a.color != b.color or a.meta != b.meta:
            bad += 1
            if bad == 1:
                print(f"✘ {name}: مسار {i} وصفه مختلف (kind/color/meta)")
        elif (a.brush_profile or []) != (b.brush_profile or []):
            bad += 1
            if bad == 1:
                print(f"✘ {name}: مسار {i} ملف الفرشاة مختلف")
    same_wh = (old.width, old.height) == (new.width, new.height)
    if bad or not same_wh:
        print(f"✘ {name}: {bad} مسارًا مختلفًا من {len(old.strokes)} · الأبعاد {same_wh}")
        all_ok = False
    else:
        pts = sum(len(s.points) for s in new.strokes)
        print(f"✔ {name}: {len(new.strokes)} مسارًا · {pts} نقطة · مطابق تمامًا لكاش النسخة القديمة")

print("النتيجة:", "مطابق تمامًا" if all_ok else "يوجد اختلاف — لا تُقبل")
raise SystemExit(0 if all_ok else 1)
