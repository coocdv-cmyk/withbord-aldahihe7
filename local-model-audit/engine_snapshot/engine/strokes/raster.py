"""تحويل الصور النقطية إلى مسارات رسم — نقل موسّع لمخطط VideoScribe.

المرجع المفكوك:
- generatePathFromSkeletons.ts: تصغير ≤ 500px → ثنائي → فصل الأشكال → تخفيف → تتبّع
- brushSize = iterations / scaleFactor   (سماكة القلم من عدد تكرارات التخفيف)
- findSeparateImageShapes.ts: مكوّنات متصلة 8-اتجاه بترتيب صفّي

تحسيناتنا:
- حد قابل للضبط (افتراضي 900px) للجودة الأعلى
- قص كل شكل لصندوقه + هامش 1px (أسرع كثيرًا بنفس النتيجة)
- وضعان للثنائية: alpha (كالأصل) أو dark (لصور فوتوغرافية بلا قناة شفافية)
"""
from __future__ import annotations

import numpy as np

from .mask_path import generate_mask_path, points_to_lengths
from .model import Stroke, StrokeDoc
from .thinning import thin

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


def binarize(img: np.ndarray, mode: str = "auto", luma_threshold: int = 200) -> np.ndarray:
    """يحوّل صورة (H,W) أو (H,W,3/4) إلى قناع حبر bool."""
    if img.ndim == 2:
        ink = img < luma_threshold
        return ink
    if img.shape[2] == 4:
        alpha = img[:, :, 3]
        if mode in ("auto", "alpha") and alpha.min() < 250:
            # صورة شفافة: الحبر = البكسلات الظاهرة (أي قناة > 0 كما عندهم)
            return (alpha > 25) | ((alpha > 0) & (img[:, :, :3].max(axis=2) > 10))
        rgb = img[:, :, :3].astype(np.float32)
    else:
        rgb = img[:, :, :3].astype(np.float32)
    luma = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    return luma < luma_threshold


def _connected_shapes(binary: np.ndarray):
    """مكوّنات متصلة 8-اتجاه بترتيب الصفوف (كما في findSeparateImageShapes)."""
    h, w = binary.shape
    if cv2 is not None:
        n, labels = cv2.connectedComponents(binary.astype(np.uint8), connectivity=8)
        shapes = []
        for i in range(1, n):
            ys, xs = np.nonzero(labels == i)
            if len(ys) == 0:
                continue
            shapes.append((int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max()), ys, xs))
        shapes.sort(key=lambda s: (s[0], s[1]))  # صفّي: أعلى ثم يسار
        return shapes
    # بديل بلا cv2: BFS بطيء نسبيًا
    visited = np.zeros_like(binary, dtype=bool)
    shapes = []
    for r in range(h):
        for c in range(w):
            if binary[r, c] and not visited[r, c]:
                stack = [(r, c)]
                visited[r, c] = True
                pts = []
                while stack:
                    y, x = stack.pop()
                    pts.append((y, x))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            yy, xx = y + dy, x + dx
                            if 0 <= yy < h and 0 <= xx < w and binary[yy, xx] and not visited[yy, xx]:
                                visited[yy, xx] = True
                                stack.append((yy, xx))
                ys = np.array([p[0] for p in pts])
                xs = np.array([p[1] for p in pts])
                shapes.append((int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max()), ys, xs))
    return shapes


def raster_to_strokes(
    img: np.ndarray,
    *,
    asset: str = "inline",
    max_size: int = 900,
    mode: str = "auto",
    luma_threshold: int = 200,
    rtl: bool = False,
    min_length: float = 2.0,
    simplify_tol: float = 0.5,
) -> StrokeDoc:
    """الصورة → StrokeDoc. هذا هو مسار «صورة حقيقية تُرسم باليد»."""
    h0, w0 = img.shape[:2]
    scale = min(max_size / max(w0, h0), 1.0)
    if scale < 1.0:
        if cv2 is not None:
            work_img = cv2.resize(img, (max(1, int(w0 * scale)), max(1, int(h0 * scale))), interpolation=cv2.INTER_AREA)
        else:  # pragma: no cover
            from PIL import Image

            work_img = np.asarray(Image.fromarray(img).resize((int(w0 * scale), int(h0 * scale))))
    else:
        work_img = img

    binary = binarize(work_img, mode=mode, luma_threshold=luma_threshold)
    h, w = binary.shape
    if not binary.any() or binary.all():
        return StrokeDoc(asset=asset, source="raster", width=w0, height=h0, strokes=[], stats={"error": "solid_or_empty"})

    strokes: list[Stroke] = []
    shapes = _connected_shapes(binary)
    for (y0, x0, y1, x1, ys, xs) in shapes:
        # قص الشكل + هامش 1
        pad = 1
        cy0, cx0 = max(0, y0 - pad), max(0, x0 - pad)
        cy1, cx1 = min(h, y1 + 1 + pad), min(w, x1 + 1 + pad)
        shape_mask = np.zeros((cy1 - cy0, cx1 - cx0), dtype=bool)
        shape_mask[ys - cy0, xs - cx0] = True

        thinned, iterations = thin(shape_mask)
        if not thinned.any():
            continue
        points = generate_mask_path(thinned, rtl=rtl)
        if not points:
            continue
        coords, lengths, jumps = points_to_lengths(points)

        # سماكة متغيرة: نصف قطر محلي من تحويل المسافة (جودة أعلى من السماكة الثابتة)
        profile: list[float] | None = None
        if cv2 is not None:
            dist = cv2.distanceTransform(shape_mask.astype(np.uint8), cv2.DIST_L2, 3)
            profile = []
            for p in points:
                yy = min(max(int(round(p["y"])), 0), shape_mask.shape[0] - 1)
                xx = min(max(int(round(p["x"])), 0), shape_mask.shape[1] - 1)
                profile.append(float(max(dist[yy, xx], 0.6)))

        # إعادة للإحداثيات الأصلية
        inv = 1.0 / scale
        coords = [[(x + cx0) * inv, (y + cy0) * inv] for x, y in coords]
        if profile is not None:
            profile = [b * inv for b in profile]
        brush = iterations / scale
        stroke = Stroke(points=coords, lengths=lengths, brush=max(brush, 1.0), kind="draw", jumps=jumps or None,
                        brush_profile=profile,
                        meta={"shape_bbox": [x0 * inv, y0 * inv, (x1 + 1) * inv, (y1 + 1) * inv]})
        if stroke.total_length >= min_length:
            strokes.append(stroke)

    # تبسيط المسارات للرندر السريع
    if simplify_tol > 0:
        from .model import simplify_stroke

        strokes = [simplify_stroke(s, tol=simplify_tol) for s in strokes]

    doc = StrokeDoc(
        asset=asset,
        source="raster",
        width=float(w0),
        height=float(h0),
        strokes=strokes,
        stats={
            "shapes": len(shapes),
            "strokes": len(strokes),
            "total_length": sum(s.total_length for s in strokes),
            "scale": scale,
            "max_size": max_size,
            "mode": mode,
        },
    )
    return doc
