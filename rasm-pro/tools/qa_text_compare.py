"""مقارنة بصرية: نصّنا المرسوم (مسارات) مقابل مرجع PIL (Raqm) — لنفس الجملة."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw, ImageFont, features  # noqa: E402

from engine.strokes import find_font, render_preview, text_to_strokes  # noqa: E402

QA = ROOT / "qa"
QA.mkdir(exist_ok=True)

text = sys.argv[1] if len(sys.argv) > 1 else "الحرب العالمية (1914-1918) بنسبة 50%"
size = int(sys.argv[2]) if len(sys.argv) > 2 else 120
font_path = find_font("cairo")

print("Raqm متاح:", features.check("raqm"))
W, H = 1500, 380

canvas = Image.new("RGB", (W, H * 2), (247, 243, 232))
d = ImageDraw.Draw(canvas)

# 1) مرجع PIL
try:
    kw = {}
    if features.check("raqm"):
        kw = {"layout_engine": ImageFont.Layout.RAQM}
    f = ImageFont.truetype(str(font_path), size, **kw)
    bbox = d.textbbox((0, 0), text, font=f, direction="rtl", features=None)
    w = bbox[2] - bbox[0]
    d.text(((W - w) / 2 - bbox[0], 60), text, font=f, fill=(30, 26, 22), direction="rtl")
    d.text((20, 20), "PIL/Raqm (مرجع)", fill=(140, 60, 40))
except Exception as e:
    d.text((20, 60), f"PIL فشل: {e}", fill=(200, 0, 0))
    print("PIL فشل:", e)

# 2) مساراتنا
doc = text_to_strokes(text, font_path, size, mode="skeleton", rtl=True)
tmp = QA / "_ours_tmp.png"
render_preview(doc, tmp, canvas=(W, H), margin=30)
canvas.paste(Image.open(tmp), (0, H))
d.text((20, H + 20), "محرّكنا (مسارات)", fill=(140, 60, 40))
tmp.unlink(missing_ok=True)

out = QA / "text_compare.png"
canvas.save(out)
print("صورة المقارنة:", out)
