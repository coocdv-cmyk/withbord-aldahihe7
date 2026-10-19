# -*- coding: utf-8 -*-
"""تكافؤ مسار القناع: التنفيذ المتجهي الجديد ضد التنفيذ المرجعي البطيء — بلا pytest.

الهدف: إثبات أن تحسين الأداء في ``mask_path._Mask`` لا يغيّر الناتج (نقطة بنقطة،
وقيمة moveTo، وترتيب المسارات) — وهو شرط بقاء كاش المسارات صالحًا.
"""
from __future__ import annotations

import numpy as np

from engine.strokes.mask_path import (
    COMPASS,
    DIRECTION_HISTORY_SAMPLE_SIZE,
    MAX_STEPS_FACTOR,
    _avg_direction,
    _count_neighbours,
    generate_mask_path,
)


# --- التنفيذ المرجعي (نسخة ما قبل التحسين، كما كانت حرفيًا) ---
def _ref_find_start_point(pixels: np.ndarray, rtl: bool):
    ys, xs = np.nonzero(pixels)
    if len(ys) == 0:
        return None
    coords = sorted(zip(ys.tolist(), xs.tolist()))
    terminals = [(y, x) for (y, x) in coords if _count_neighbours(pixels, y, x) == 1]
    candidates = terminals if terminals else coords
    if rtl:
        return max(candidates, key=lambda pt: (pt[1], -pt[0]))
    return candidates[0]


def _ref_find_near_point(pixels: np.ndarray, y: int, x: int, last_dir):
    h, w = pixels.shape
    directions = list(COMPASS)
    if last_dir is not None:
        idx = next((i for i, (deg, _, _) in enumerate(directions) if deg == last_dir), None)
        if idx:
            directions = directions[idx:] + directions[:idx]
    neighbours = []
    for deg, dy, dx in directions:
        yy, xx = y + dy, x + dx
        if 0 <= yy < h and 0 <= xx < w and pixels[yy, xx]:
            neighbours.append((deg, dy, dx))
    if not neighbours:
        return None
    if len(neighbours) == 1:
        chosen = neighbours[0]
    else:
        ref = directions[0][0] if last_dir is not None else neighbours[0][0]
        chosen = min(neighbours, key=lambda nb: abs(ref - nb[0]))
    _, dy, dx = chosen
    pixels[y + dy, x + dx] = False
    return (y + dy, x + dx), chosen[0]


def _ref_trace(pixels: np.ndarray, start):
    points = [start]
    teleports = set()
    last_good = start
    hist: list[int] = []
    direction = None
    current = start
    max_steps = pixels.size * MAX_STEPS_FACTOR
    steps = 0
    while steps < max_steps:
        steps += 1
        if _count_neighbours(pixels, *current) >= 2:
            last_good = current
        if hist:
            direction = _avg_direction(hist)
        found = _ref_find_near_point(pixels, current[0], current[1], direction)
        if found:
            nxt, direction = found
            hist.append(direction)
            if len(hist) > DIRECTION_HISTORY_SAMPLE_SIZE:
                hist.pop(0)
            points.append(nxt)
            current = nxt
        else:
            if _count_neighbours(pixels, *last_good) > 0 and last_good != current:
                current = last_good
                hist.clear()
                direction = None
                teleports.add(len(points))
            else:
                break
    return points, teleports


def ref_generate_mask_path(pixels: np.ndarray, rtl: bool = False) -> list[dict]:
    work = pixels.astype(bool).copy()
    out: list[dict] = []
    while True:
        start = _ref_find_start_point(work, rtl)
        if start is None:
            break
        work[start[0], start[1]] = False
        pts, teleports = _ref_trace(work, start)
        for i, (y, x) in enumerate(pts):
            out.append({"x": x, "y": y, "moveTo": i == 0 or i in teleports})
    return out


def _eq(a: list[dict], b: list[dict]) -> None:
    assert len(a) == len(b), f"عدد النقاط مختلف: {len(a)} != {len(b)}"
    for i, (pa, pb) in enumerate(zip(a, b)):
        assert pa == pb, f"نقطة {i}: {pa} != {pb}"


# --- أقنعة الاختبار ---
def _ring(width: int = 5, r: int = 70) -> np.ndarray:
    import math

    size = 2 * r + 20
    m = np.zeros((size, size), dtype=bool)
    for a in np.linspace(0, 2 * math.pi, 4000):
        cy, cx = r + 10 + r * math.sin(a), r + 10 + r * math.cos(a)
        for dy in range(-(width // 2), width // 2 + 1):
            for dx in range(-(width // 2), width // 2 + 1):
                m[int(round(cy)) + dy, int(round(cx)) + dx] = True
    return m


def _stroke_ring(width: int = 3) -> np.ndarray:
    """حلقة غير مغلقة (نهايات حرة) — تختبر اختيار نقطة البداية."""
    import math

    m = np.zeros((160, 160), dtype=bool)
    for a in np.linspace(0.4, 5.6, 3000):
        cy, cx = 80 + 60 * math.sin(a), 80 + 60 * math.cos(a)
        m[int(cy), int(cx)] = True
        if width > 1:
            for k in range(1, width):
                m[int(cy) + k, int(cx)] = True
    return m


def _blobs(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    m = np.zeros((90, 130), dtype=bool)
    for _ in range(rng.integers(3, 7)):
        y0, x0 = int(rng.integers(0, 80)), int(rng.integers(0, 120))
        h, w = int(rng.integers(1, 18)), int(rng.integers(1, 22))
        m[y0 : y0 + h, x0 : x0 + w] = True
    return m


def test_ring_equivalence():
    m = _ring()
    for rtl in (False, True):
        _eq(generate_mask_path(m, rtl=rtl), ref_generate_mask_path(m, rtl=rtl))


def test_open_stroke_equivalence():
    m = _stroke_ring()
    for rtl in (False, True):
        _eq(generate_mask_path(m, rtl=rtl), ref_generate_mask_path(m, rtl=rtl))


def test_random_blobs_equivalence():
    for seed in (1, 2, 3, 7, 11, 23):
        m = _blobs(seed)
        for rtl in (False, True):
            _eq(generate_mask_path(m, rtl=rtl), ref_generate_mask_path(m, rtl=rtl))


def test_text_word_equivalence():
    """كلمة عربية حقيقية: تخانة Guo-Hall ثم المسار — مقارنة مرجعية كاملة."""
    from engine.strokes import find_font
    from engine.strokes.thinning import thin
    from engine.strokes.text_paths import text_to_strokes

    font = find_font("arefruqaa")
    doc = text_to_strokes("بسم الله", font, 180, mode="skeleton", rtl=True)
    m = np.zeros((300, 900), dtype=bool)
    from PIL import Image, ImageDraw

    im = Image.new("L", (900, 300), 0)
    d = ImageDraw.Draw(im)
    for st in doc.strokes:
        d.line([tuple(p) for p in st.points], fill=255, width=max(2, int(round(st.brush))))
    m = np.asarray(im) > 127
    th, _it = thin(m)
    for rtl in (True, False):
        _eq(generate_mask_path(th, rtl=rtl), ref_generate_mask_path(th, rtl=rtl))


def test_photo_trace_equivalence_small():
    """صورة حقيقية (مصغّرة) — مقارنة كاملة للمسار المرجعي."""
    from pathlib import Path

    import numpy as np
    from PIL import Image

    p = Path(__file__).resolve().parents[1] / "projects" / "ww1" / "assets" / "event-معركة-السوم" / "c75888b731eb.jpg"
    if not p.exists():
        return  # لا أصل محليًا → لا اختبار (لا نجاح وهمي)
    img = np.asarray(Image.open(p).convert("L"))
    small = img[::6, ::6]
    m = small < 130
    from engine.strokes.thinning import thin

    th, _it = thin(m)
    _eq(generate_mask_path(th, rtl=False), ref_generate_mask_path(th, rtl=False))
