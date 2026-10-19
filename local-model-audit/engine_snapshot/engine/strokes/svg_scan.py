"""قراءة SVG → أوامر رسم متجهية حقيقية (مسارات + أطوال + سماكة من stroke-width).

المرجع المفكوك: playback/pixi-player/helpers/getDrawCommandsFromSVGElements.ts
- لكل عنصر هندسي: totalLength ثم نقاط مع pathLength لكل مقطع
- brushSize = stroke-width × معامل المقياس

تحسيناتنا: تقسيم المسارات الفرعية، تصنيف stroke/fill، تبسيط تلقائي، ودعم التحويلات عبر reify.
"""
from __future__ import annotations

import math
from pathlib import Path

from svgelements import Move, Path as SVGPath, Shape, SVG

from .model import Stroke, StrokeDoc

DEFAULT_STROKE_WIDTH = 2.0


def _split_subpaths(path: SVGPath) -> list[SVGPath]:
    """يقسّم مسار SVG إلى مسارات فرعية عند كل Move."""
    subs: list[SVGPath] = []
    cur: list = []
    for seg in path:
        if isinstance(seg, Move):
            if cur:
                subs.append(SVGPath(*cur))
            cur = [seg]
        else:
            cur.append(seg)
    if cur:
        subs.append(SVGPath(*cur))
    return subs


def _sample_path(path: SVGPath, step: float, min_points: int = 4, max_points: int = 6000):
    """يعيد نقاطًا موزعة على طول المسار + أطوالًا تراكمية (بوحدات المستخدم)."""
    try:
        total = float(path.length())
    except Exception:
        total = 0.0
    if total <= 0:
        # مسار قصير جدًا: نقطتان
        try:
            p0, p1 = path.point(0.0), path.point(1.0)
        except Exception:
            return [], []
        pts = [[float(p0.x), float(p0.y)], [float(p1.x), float(p1.y)]]
        return pts, [0.0, math.dist(pts[0], pts[1])]

    n = int(max(min_points, min(max_points, math.ceil(total / max(step, 0.05)))))
    pts: list[list[float]] = []
    lens: list[float] = []
    prev = None
    for i in range(n + 1):
        t = i / n
        try:
            pt = path.point(t)
        except Exception:
            continue
        xy = [float(pt.x), float(pt.y)]
        if prev is None:
            lens.append(0.0)
        else:
            lens.append(lens[-1] + math.dist(prev, xy))
        pts.append(xy)
        prev = xy
    return pts, lens


def scan_svg(
    source: str | Path,
    *,
    asset: str | None = None,
    step: float = 2.0,
    min_length: float = 1.0,
    simplify_tol: float = 0.4,
    include_fills: bool = True,
) -> StrokeDoc:
    """SVG (ملف أو نص) → StrokeDoc بمسارات حقيقية."""
    svg = SVG.parse(str(source), reify=True)
    asset_id = asset or (Path(source).name if isinstance(source, (str, Path)) and Path(str(source)).exists() else "inline-svg")

    vb = getattr(svg, "viewbox", None)
    vb_x = float(getattr(vb, "x", 0) or 0)
    vb_y = float(getattr(vb, "y", 0) or 0)
    vb_w = float(getattr(vb, "width", 0) or 0)
    vb_h = float(getattr(vb, "height", 0) or 0)
    width = float(getattr(svg, "width", 0) or vb_w or 0)
    height = float(getattr(svg, "height", 0) or vb_h or 0)

    strokes: list[Stroke] = []
    seen = 0
    for el in svg.elements():
        if isinstance(el, (SVG,)) or not isinstance(el, Shape):
            continue
        p = getattr(el, "path", None)
        if p is None and isinstance(el, SVGPath):
            p = el
        if not isinstance(p, SVGPath):
            continue

        stroke_attr = getattr(el, "stroke", None)
        fill_attr = getattr(el, "fill", None)
        sw = getattr(el, "stroke_width", None)
        try:
            brush = float(sw) if sw is not None else DEFAULT_STROKE_WIDTH
        except Exception:
            brush = DEFAULT_STROKE_WIDTH
        brush = max(brush, 0.5)

        is_none_stroke = stroke_attr is None or str(stroke_attr).lower() in ("none", "transparent")
        is_none_fill = fill_attr is None or str(fill_attr).lower() in ("none", "transparent")

        for sub in _split_subpaths(p):
            pts, lens = _sample_path(sub, step=step)
            if len(pts) < 2 or (lens and lens[-1] < min_length):
                continue
            # إزاحة الـ viewBox إلى الأصل
            pts = [[x - vb_x, y - vb_y] for x, y in pts]

            # مغلق؟ (نقطة البداية ≈ النهاية)
            closed = math.dist(pts[0], pts[-1]) <= max(0.75, brush * 0.5)
            if closed and math.dist(pts[0], pts[-1]) > 0:
                pts.append(list(pts[0]))
                lens = lens + [lens[-1] + math.dist(pts[-2], pts[-1])]

            if closed and not is_none_fill and is_none_stroke:
                kind = "fill"
            elif closed and not is_none_fill and not is_none_stroke:
                kind = "draw"      # مرسوم ثم يُملأ لاحقًا
            else:
                kind = "draw"
                if is_none_stroke and not is_none_fill:
                    kind = "fill"
            seen += 1
            strokes.append(
                Stroke(
                    points=pts,
                    lengths=lens,
                    brush=brush,
                    kind=kind,
                    meta={
                        "fill_color": str(fill_attr) if not is_none_fill else None,
                        "stroke_color": str(stroke_attr) if not is_none_stroke else None,
                    },
                )
            )

    if simplify_tol > 0:
        from .model import simplify_stroke

        strokes = [simplify_stroke(s, tol=simplify_tol) for s in strokes]

    if include_fills:
        # الفئات المرسومة أولًا (draw) ثم التعبئة (fill) — ترتيب الكشف الكلاسيكي
        strokes = [s for s in strokes if s.kind == "draw"] + [s for s in strokes if s.kind == "fill"]

    doc = StrokeDoc(
        asset=asset_id,
        source="svg",
        width=width or vb_w,
        height=height or vb_h,
        view_box=[vb_x, vb_y, vb_w, vb_h],
        strokes=strokes,
        stats={
            "elements": seen,
            "strokes": len(strokes),
            "total_length": sum(s.total_length for s in strokes),
        },
    )
    return doc
