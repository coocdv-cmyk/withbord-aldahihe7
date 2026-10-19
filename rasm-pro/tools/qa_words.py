"""لقطة تكبير لكلمات حساسة (نقاط ووصلات) — للفحص البصري."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw  # noqa: E402

from engine.strokes import find_font, render_preview, text_to_strokes  # noqa: E402

QA = ROOT / "qa"
QA.mkdir(exist_ok=True)

words = sys.argv[1:] or ["بيت", "دجاجة", "الجنود", "النمسا"]
font = find_font("cairo")
W, H = 700, 300
canvas = Image.new("RGB", (W, len(words) * H), (247, 243, 232))
d = ImageDraw.Draw(canvas)
for i, w in enumerate(words):
    doc = text_to_strokes(w, font, 170, mode="skeleton", rtl=True)
    tmp = QA / "_w_tmp.png"
    render_preview(doc, tmp, canvas=(W, H), margin=16)
    canvas.paste(Image.open(tmp), (0, i * H))
    d.text((10, i * H + 8), w, fill=(150, 60, 40))
    tmp.unlink(missing_ok=True)
out = QA / "text_words.png"
canvas.save(out)
print("صورة:", out)
