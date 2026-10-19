"""ترتيب الرسم: قراءة صفّية (مثل VideoScribe) أو تقليل حركة القلم (أذكى).

- reading: نطاقات أفقية (bands) ثم من اليسار لليمين — الترتيب الطبيعي للعين.
- travel: جشِع يقلّل مسافة انتقال القلم مع احترام أولوية القراءة (وزن).
- rtl_reading: للعربية — داخل النص من اليمين.
"""
from __future__ import annotations

import math

from .model import Stroke


def _band_key(stroke: Stroke, band_h: float, rtl: bool):
    x0, y0, x1, y1 = stroke.bbox
    cy = (y0 + y1) / 2
    band = int(cy / max(band_h, 1e-6))
    return (band, -x0 if rtl else x0, y0)


def order_reading(strokes: list[Stroke], image_height: float, band_ratio: float = 0.16, rtl: bool = False) -> list[Stroke]:
    band_h = max(image_height * band_ratio, 8.0)
    return sorted(strokes, key=lambda s: _band_key(s, band_h, rtl))


def order_travel(strokes: list[Stroke], image_height: float, band_ratio: float = 0.16, rtl: bool = False,
                 lookahead: int = 8, priority: float = 0.6) -> list[Stroke]:
    """ترتيب يقلل حركة القلم مع الحفاظ على القراءة.

    priority: وزن الأولوية الصفّية (0 = حركة أقل تمامًا، 1 = قراءة خالصة).
    """
    if not strokes:
        return []
    band_h = max(image_height * band_ratio, 8.0)
    ranked = order_reading(strokes, image_height, band_ratio, rtl)
    rank = {id(s): i for i, s in enumerate(ranked)}
    remaining = list(ranked)
    out: list[Stroke] = ranked[:1]
    remaining.remove(out[0])
    scale = max(image_height, 1.0)
    while remaining:
        pen = out[-1].end()
        best = None
        best_cost = float("inf")
        for cand in remaining[:lookahead]:
            d = math.dist(pen, cand.start()) / scale
            rp = rank[id(cand)] / max(len(strokes) - 1, 1)
            cost = d + priority * rp * 0.5
            if cost < best_cost:
                best, best_cost = cand, cost
        remaining.remove(best)
        out.append(best)
    return out


def order_strokes(strokes: list[Stroke], image_height: float, mode: str = "reading", rtl: bool = False) -> list[Stroke]:
    if mode == "travel":
        return order_travel(strokes, image_height, rtl=rtl)
    return order_reading(strokes, image_height, rtl=rtl)
