"""تشخيص تشكيل النص: هل المخرجات مقلوبة؟ (يقارن ترتيب الحروف المرسوم فعليًا)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from engine.strokes import find_font, render_preview, text_to_strokes  # noqa: E402
from engine.strokes.text_paths import _shape_line  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

QA = ROOT / "qa"
QA.mkdir(exist_ok=True)

font = find_font("cairo")
print("خط الاختبار:", font.name)

tt = TTFont(str(font), lazy=True)
order = tt.getGlyphOrder()

samples = [
    "الحرب 1914",
    "في صيف عام 1914، اشتعلت الحرب.",
    "World War I",
]
for s in samples:
    glyphs, width, rtl, upem, scale = _shape_line(s, font, 100)
    print(f"\n=== {s!r} → rtl={rtl} width={width:.1f}")
    for g in glyphs[:12]:
        nm = order[g["gid"]] if g["gid"] < len(order) else "?"
        print(f"   gid={g['gid']:5d} {nm:20s} cluster={g['cluster']:3d} x={g['x']:8.1f} adv={g['advance']:7.1f}")

# صور للفحص البصري
for i, s in enumerate(["الحرب 1914", "في صيف عام 1914، اشتعلت الحرب.", "الحرب العالمية الأولى (1914-1918) بنسبة 50%"], 1):
    doc = text_to_strokes(s, font, 120, mode="skeleton", rtl=True)
    out = QA / f"text_check_{i}.png"
    render_preview(doc, out, canvas=(1400, 300), margin=24)
    print("صورة:", out)
