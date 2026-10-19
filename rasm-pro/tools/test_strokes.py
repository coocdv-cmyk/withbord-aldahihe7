"""اختبار شامل لمحرك المسارات: SVG + نص عربي + صورة → معاينات PNG."""
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.strokes import (  # noqa: E402
    find_font,
    raster_to_strokes,
    render_preview,
    render_strip,
    scan_svg,
    text_to_strokes,
)

OUT = Path(r"C:\Users\USER\AppData\Local\Temp\opencode\rasm-preview")
OUT.mkdir(parents=True, exist_ok=True)

report = []

# ---------- 1) SVG حقيقي من مكتبة Lucide ----------
svg_files = list(Path(r"D:\withbord inmation\studio\library").rglob("*.svg"))
print(f"SVG متاح: {len(svg_files)}")
pick = None
for want in ("globe", "landmark", "brain", "user", "map"):
    pick = next((f for f in svg_files if f.stem == want), None)
    if pick:
        break
pick = pick or svg_files[0]
t0 = time.time()
doc_svg = scan_svg(str(pick))
t1 = time.time()
render_preview(doc_svg, OUT / "01_svg.png", canvas=(700, 700))
report.append(f"SVG: {pick.name} → {len(doc_svg.strokes)} مسار، طول كلي {doc_svg.total_length():.0f}، زمن {t1-t0:.2f}s")

# ---------- 2) نص عربي (وضعان) ----------
ar_text = "الحرب العالمية الأولى"
font = find_font("arefruqaa")
t0 = time.time()
doc_skel = text_to_strokes(ar_text, font, 110, mode="skeleton")
t1 = time.time()
render_preview(doc_skel, OUT / "02_text_skeleton.png", canvas=(1200, 320))
render_strip(doc_skel, OUT / "02_text_skeleton_strip.png", steps=5, cell=(600, 160))
report.append(f"نص skeleton: {len(doc_skel.strokes)} مسار، طول {doc_skel.total_length():.0f}، زمن {t1-t0:.2f}s")

t0 = time.time()
doc_out = text_to_strokes(ar_text, font, 110, mode="outline")
t1 = time.time()
render_preview(doc_out, OUT / "03_text_outline.png", canvas=(1200, 320))
report.append(f"نص outline: {len(doc_out.strokes)} مسار، طول {doc_out.total_length():.0f}، زمن {t1-t0:.2f}s")

# ---------- 3) صورة نقطية → مسارات ----------
src = Image.new("L", (1600, 420), 255)
d = ImageDraw.Draw(src)
try:
    f = ImageFont.truetype(str(find_font("amiri")), 250)
    d.text((60, 70), "السلام عليكم", font=f, fill=0)
except Exception as e:
    d.ellipse((100, 60, 500, 360), outline=0, width=22)
    d.line((520, 360, 900, 60), fill=0, width=22)
    d.rectangle((950, 80, 1450, 340), outline=0, width=22)
    print("PIL بلا تشكيل عربي — رسم أشكال هندسية")
src.save(OUT / "04_raster_src.png")

t0 = time.time()
doc_ras = raster_to_strokes(np.array(src.convert("RGB")), luma_threshold=128)
t1 = time.time()
render_preview(doc_ras, OUT / "05_raster_strokes.png", canvas=(1200, 340))
render_strip(doc_ras, OUT / "05_raster_strip.png", steps=4, cell=(700, 200))
report.append(f"صورة: {len(doc_ras.strokes)} مسار، طول {doc_ras.total_length():.0f}، زمن {t1-t0:.2f}s")

# ---------- 4) نص لاتيني (اختبار LTR) ----------
font_en = find_font("archivo", prefer_bold=True)
doc_en = text_to_strokes("World War I", font_en, 120, mode="skeleton")
render_preview(doc_en, OUT / "06_latin.png", canvas=(900, 250))
report.append(f"لاتيني: {len(doc_en.strokes)} مسار")

print("\n=== التقرير ===")
for r in report:
    print(" •", r)
print("المعاينات في:", OUT)
