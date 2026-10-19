"""تتبّع مسار الرسم من خط مُخفَّف — نقلة حرفية لخوارزمية VideoScribe.

المرجع المفكوك: shared/helpers/text-draw.ts → generateMaskPath / traceFromPoint / findNearPoint

الفكرة:
- نبدأ من نقطة طرفية (جيران=1) إن وُجدت، وإلا أي بكسل حبر.
- نتحرك في 8 اتجاهات (بوصلة 45°) مع "تاريخ اتجاه" (متوسط آخر 5 خطوات) لاختيار الاتجاه الأقرب.
- في التفرّعات نختار الجار الأقرب لاتجاه السير.
- نمسح كل بكسل نزوره، وعند الانحشار نعود لآخر نقطة "جيدة" (جيران ≥ 2) ونكمل.
- عند العجز نبدأ مسارًا جديدًا من أول نقطة حبر متبقية (moveTo=True).
- للعربية (RTL) نبدأ من أقصى اليمين (كما في كودهم: isTextRTL).
"""
from __future__ import annotations

import math

import numpy as np

__all__ = ["generate_mask_path", "points_to_lengths"]

# اتجاهات البوصلة بالدرجات → (dy, dx) — مطابقة تمامًا للمصفوفة الأصلية
COMPASS: list[tuple[int, int, int]] = [
    (0, -1, 0),    # N
    (45, -1, -1),  # NE
    (90, 0, -1),   # W
    (135, 1, -1),  # SW
    (180, 1, 0),   # S
    (225, 1, 1),   # SE
    (270, 0, 1),   # E
    (315, -1, 1),  # NW
]

DIRECTION_HISTORY_SAMPLE_SIZE = 5
MAX_STEPS_FACTOR = 4  # حماية من الحلقات اللانهائية (× عدد البكسلات)


def _count_neighbours(pixels: np.ndarray, y: int, x: int) -> int:
    """العدّ المرجعي البطيء (بايثون) — يُستخدم في اختبار التكافؤ فقط."""
    h, w = pixels.shape
    n = 0
    for _deg, dy, dx in COMPASS:
        yy, xx = y + dy, x + dx
        if 0 <= yy < h and 0 <= xx < w and pixels[yy, xx]:
            n += 1
    return n


class _Mask:
    """قناع ثنائي + عدّاد جوار متزامن (تحديث موضعي O(1)).

    Phase 3.1 (أداء): العدّ داخل حلقة بايثون لكل بكسل كان 87 ثانية من 119 ثانية
    في تتبّع صورة 900px (47.5 مليون نداء). العدّاد يُبنى متجهيًا مرة واحدة
    ويُحدَّث عند كل مسح بكسل (8 جيران)، فتبقى القيم مطابقة تمامًا للعدّ المرجعي
    وبنفس ترتيب المسارات (اختبار تكافؤ: tests/test_mask_path_equiv.py).
    """

    __slots__ = ("px", "cnt")

    def __init__(self, pixels: np.ndarray):
        px = pixels.astype(bool).copy()
        self.px = px
        h, w = px.shape
        pad = np.pad(px, 1, constant_values=False)
        cnt = np.zeros((h, w), dtype=np.int16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    cnt += pad[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
        cnt[~px] = 0
        self.cnt = cnt

    def neighbours(self, y: int, x: int) -> int:
        return int(self.cnt[y, x])

    def clear(self, y: int, x: int) -> None:
        """يمسح بكسلًا ويُنقص عدّاد جيرانه الثمانية.

        مهم: عدّاد البكسل نفسه لا يتغيّر (البكسل لا يُعدّ جارًا لنفسه)، ومسحه
        لا يمسّ قيمته — والتتبّع يقرأ عدّاد ``current`` بعد مسحه فعلًا، فلو
        صفّرناه لتغيّر قرار ``last_good`` واختلف الناتج.
        """
        if not self.px[y, x]:
            return
        self.px[y, x] = False
        h, w = self.px.shape
        y0, y1 = (y - 1 if y else 0), min(h, y + 2)
        x0, x1 = (x - 1 if x else 0), min(w, x + 2)
        self.cnt[y0:y1, x0:x1] -= 1
        self.cnt[y, x] += 1  # إلغاء إنقاص الذات


def _find_start_point(mask: _Mask, rtl: bool) -> tuple[int, int] | None:
    px, cnt = mask.px, mask.cnt
    if not px.any():
        return None
    term = px & (cnt == 1)
    ys, xs = np.nonzero(term if term.any() else px)
    if rtl:
        # للنص العربي: أقصى اليمين، ثم الأعلى (لا الأسفل — كان يقلب موضع البداية)
        mx = int(xs.max())
        return int(ys[xs == mx].min()), mx
    # لغير العربي: الأعلى ثم الأيسر (نفس ترتيب sorted(zip(ys, xs)))
    my = int(ys.min())
    return my, int(xs[ys == my].min())


def _avg_direction(direction_history: list[int]) -> int:
    total = sum(direction_history)
    if total == 0:
        return 0
    avg = total / len(direction_history)
    left = int(np.ceil(avg / 45.0)) * 45
    right = int(np.floor(avg / 45.0)) * 45
    return right if abs(avg - left) > abs(avg - right) else left


def _find_near_point(mask: _Mask, y: int, x: int, last_dir: int | None):
    pixels = mask.px
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
    mask.clear(y + dy, x + dx)
    return (y + dy, x + dx), chosen[0]


def _trace_from_point(mask: _Mask, start: tuple[int, int]):
    """يطابق traceFromPoint: يعيد (النقاط، مؤشرات الطفرات).

    الطفرة = العودة إلى ``last_good`` بعد انحشار المسار — تُعلَّم هنا لتُصبح
    «رفع قلم» (moveTo) عند بناء المسار، فلا يُرسم خط مستقيم عبر الفراغ أبدًا.
    """
    points = [start]
    teleports: set[int] = set()
    last_good = start
    direction_history: list[int] = []
    direction: int | None = None
    current = start
    max_steps = mask.px.size * MAX_STEPS_FACTOR
    steps = 0

    while steps < max_steps:
        steps += 1
        if mask.neighbours(*current) >= 2:
            last_good = current
        if direction_history:
            direction = _avg_direction(direction_history)

        found = _find_near_point(mask, current[0], current[1], direction)
        if found:
            nxt, direction = found
            direction_history.append(direction)
            if len(direction_history) > DIRECTION_HISTORY_SAMPLE_SIZE:
                direction_history.pop(0)
            points.append(nxt)
            current = nxt
        else:
            if mask.neighbours(*last_good) > 0 and last_good != current:
                current = last_good
                direction_history.clear()
                direction = None
                # القفزة: النقطة القادمة تبدأ مقطعًا جديدًا بلا رسم المسافة
                teleports.add(len(points))
            else:
                break
    return points, teleports


def generate_mask_path(pixels: np.ndarray, rtl: bool = False) -> list[dict]:
    """المدخل: مصفوفة bool (True=حبر). المخرج: نقاط [{x, y, moveTo}] بترتيب الرسم.

    ``moveTo`` يُوضع عند بداية كل مسار فرعي *وعند كل طفرة* — فلا توجد قطعة
    مستقيمة عبر الفراغ (إصلاح Phase 3.1 لعيب «الخط الطويل» المرئي).
    """
    mask = _Mask(pixels)
    out: list[dict] = []
    while True:
        start = _find_start_point(mask, rtl)
        if start is None:
            break
        mask.clear(*start)
        pts, teleports = _trace_from_point(mask, start)
        for i, (y, x) in enumerate(pts):
            out.append({"x": x, "y": y, "moveTo": i == 0 or i in teleports})
    return out


def points_to_lengths(points: list[dict]) -> tuple[list[list[float]], list[float], list[int]]:
    """يحوّل النقاط إلى [[x,y]] + أطوال تراكمية (مستمرة) + مؤشرات رفع القلم (بدايات مسارات فرعية)."""
    coords: list[list[float]] = []
    lengths: list[float] = []
    jumps: list[int] = []
    total = 0.0
    prev: list[float] | None = None
    for i, p in enumerate(points):
        xy = [float(p["x"]), float(p["y"])]
        if p.get("moveTo") and prev is not None:
            jumps.append(i)
            lengths.append(total)  # القفزة لا تُحسب طولًا (لا يُرسم خط بين النقطتين)
        elif prev is None:
            lengths.append(0.0)
        else:
            total += math.hypot(xy[0] - prev[0], xy[1] - prev[1])
            lengths.append(total)
        coords.append(xy)
        prev = xy
    return coords, lengths, jumps
