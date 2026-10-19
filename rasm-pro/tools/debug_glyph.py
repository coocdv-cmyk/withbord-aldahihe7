"""تشخيص لكل حرف: هل أنتج مسارات؟ أين اختفت النقاط؟"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from engine.strokes import find_font, text_to_strokes  # noqa: E402
from engine.strokes.thinning import thin  # noqa: E402
from engine.strokes.mask_path import generate_mask_path, points_to_lengths  # noqa: E402
from engine.strokes.text_paths import _fill_contours_evenodd, _FontShaper, _contours_from_recording  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from fontTools.misc.transform import Transform  # noqa: E402
from fontTools.pens.recordingPen import RecordingPen  # noqa: E402
from fontTools.pens.transformPen import TransformPen  # noqa: E402
import math  # noqa: E402
import numpy as np  # noqa: E402

font = find_font("cairo")
text = sys.argv[1] if len(sys.argv) > 1 else "بيت"
size = 170.0

tt = TTFont(str(font), lazy=True)
glyph_set = tt.getGlyphSet()
order = tt.getGlyphOrder()
upem = tt["head"].unitsPerEm

sh = _FontShaper(font)
glyphs, width, base_rtl = sh.shape_line(text, size, force_rtl=True)
print(f"نص={text!r} عرض={width:.1f} rtl={base_rtl} حروف={len(glyphs)}")

for g in glyphs:
    gid = g["gid"]
    name = order[gid] if gid < len(order) else None
    if name is None:
        print(f"  gid={gid}: بلا اسم")
        continue
    rec = RecordingPen()
    s = size / upem
    transform = Transform(s, 0, 0, -s, g["x"], 100 - g["y"] * 1.0)
    tpen = TransformPen(rec, transform)
    glyph_set[name].draw(tpen)
    contours = _contours_from_recording(rec)
    if not contours:
        print(f"  gid={gid} {name}: بلا كنتورات")
        continue
    xs = [p[0] for c, _ in contours for p in c]
    ys = [p[1] for c, _ in contours for p in c]
    gx0, gy0, gx1, gy1 = min(xs), min(ys), max(xs), max(ys)
    w = int(math.ceil(gx1 - gx0)) + 6
    h = int(math.ceil(gy1 - gy0)) + 6
    rs = 2
    scaled = [([[(x - gx0 + 3) * rs, (y - gy0 + 3) * rs] for x, y in c], cl) for c, cl in contours]
    mask = _fill_contours_evenodd(scaled, w * rs, h * rs)
    n_pts = int(mask.sum())
    thinned, iterations = thin(mask)
    n_thin = int(thinned.sum()) if hasattr(thinned, "sum") else -1
    pts = generate_mask_path(thinned, rtl=True)
    print(f"  gid={gid} {name}: كنتورات={len(contours)} bbox=({gx0:.0f},{gy0:.0f},{gx1:.0f},{gy1:.0f}) "
          f"ماسك={n_pts} مقلّم={n_thin} iter={iterations} نقاط_المسار={len(pts)}")

doc = text_to_strokes(text, font, size, mode="skeleton", rtl=True)
print(f"المستند: مسارات={len(doc.strokes)} عرض={doc.width:.0f} ارتفاع={doc.height:.0f}")
for st in doc.strokes:
    print(f"   مسار: نقاط={len(st.points)} طول={st.total_length:.0f} brush={st.brush:.1f} "
          f"profile={'نعم:' + str(len(st.brush_profile)) if st.brush_profile else 'لا'}",
          f"bbox=({st.bbox[0]:.0f},{st.bbox[1]:.0f},{st.bbox[2]:.0f},{st.bbox[3]:.0f})")
