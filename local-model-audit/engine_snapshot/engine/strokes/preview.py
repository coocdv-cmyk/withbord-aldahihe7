"""معاينة بصرية سريعة للمسارات — PNG لعرض التقدّم (اختبار + مراجعة بشرية)."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from .model import StrokeDoc


def render_preview(
    doc: StrokeDoc,
    out_path: str | Path,
    *,
    canvas: tuple[int, int] = (1200, 800),
    progress: float = 1.0,
    bg: str = "#F7F3E8",
    ink: str = "#1F1B16",
    margin: int = 40,
    show_points: bool = False,
) -> Path:
    """يرسم المسارات حتى نسبة تقدّم معيّنة (0..1) داخل لوحة."""
    W, H = canvas
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    if doc.width <= 0 or doc.height <= 0 or not doc.strokes:
        img.save(out_path)
        return Path(out_path)

    scale = min((W - 2 * margin) / doc.width, (H - 2 * margin) / doc.height)
    ox = (W - doc.width * scale) / 2
    oy = (H - doc.height * scale) / 2

    total_len = doc.total_length() or 1.0
    budget = progress * total_len
    consumed = 0.0

    for stroke in doc.strokes:
        if consumed >= budget:
            break
        local_budget = min(stroke.total_length, budget - consumed)
        consumed += stroke.total_length

        pts = [(ox + x * scale, oy + y * scale) for x, y in stroke.points]
        widths = max(1, int(round(stroke.brush * scale)))

        # نقاط حتى الميزانية
        drawn: list[tuple[float, float]] = []
        drawn_idx: list[int] = []
        for i, p in enumerate(pts):
            L = stroke.lengths[i] if i < len(stroke.lengths) else 0.0
            drawn.append(p)
            drawn_idx.append(i)
            if not (L <= local_budget or local_budget >= stroke.total_length):
                break

        if not drawn:
            continue

        profile = stroke.brush_profile
        if profile:
            # سماكة متغيرة: دوائر متلاصقة بنصف قطر محلي
            last = None
            for i, p in zip(drawn_idx, drawn):
                r = max(0.6, float(profile[i]) * scale) if i < len(profile) else widths / 2
                if last is not None and math.hypot(p[0] - last[0], p[1] - last[1]) < max(r * 0.45, 0.8):
                    continue
                draw.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=ink)
                last = p
        else:
            if len(drawn) >= 2:
                draw.line(drawn, fill=ink, width=widths, joint="curve")
            r = widths / 2
            for p in (drawn[0], drawn[-1]):
                draw.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=ink)

        if show_points:
            for p in drawn[:: max(1, len(drawn) // 200)]:
                draw.ellipse((p[0] - 1, p[1] - 1, p[0] + 1, p[1] + 1), fill="#B23A2E")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return Path(out_path)


def render_strip(doc: StrokeDoc, out_path: str | Path, *, steps: int = 6, cell: tuple[int, int] = (600, 400)) -> Path:
    """شريط تقدّم (6 لقطات) — لمراجعة إيقاع الرسم."""
    from PIL import Image as _I

    W, H = cell
    strip = _I.new("RGB", (W, H * steps), "#FFFFFF")
    for i in range(steps):
        p = (i + 1) / steps
        tmp = Path(out_path).with_suffix(f".p{i}.png")
        render_preview(doc, tmp, canvas=cell, progress=p)
        strip.paste(_I.open(tmp), (0, i * H))
        tmp.unlink(missing_ok=True)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    strip.save(out_path)
    return Path(out_path)
