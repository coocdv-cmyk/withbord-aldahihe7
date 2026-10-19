# -*- coding: utf-8 -*-
"""تحديد عنق الزجاجة الحقيقي في تتبّع الصور (raster_to_strokes) — cProfile.

تشغيل: .venv\\Scripts\\python.exe tools\\perf_raster_profile.py
"""
from __future__ import annotations

import cProfile
import io
import pstats
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from engine.strokes.raster import raster_to_strokes  # noqa: E402

OUT = ROOT / "qa" / "phase31_perf"
OUT.mkdir(parents=True, exist_ok=True)
IMG = ROOT / "projects" / "ww1" / "assets" / "event-معركة-السوم" / "c75888b731eb.jpg"

img = np.asarray(Image.open(IMG).convert("RGB"))
print("صورة:", img.shape, "KB:", round(IMG.stat().st_size / 1024))

pr = cProfile.Profile()
pr.enable()
doc = raster_to_strokes(img, max_size=900)
pr.disable()
print("مسارات:", len(doc.strokes))

s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
ps.print_stats(28)
txt = s.getvalue()
(OUT / "profile_raster.txt").write_text(txt, encoding="utf-8")
print(txt[:6000])
