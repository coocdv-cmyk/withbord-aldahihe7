"""تخفيف الخط: Zhang-Suen ثم Guo-Hall — تنفيذ متجهي (numpy) مطابق لخوارزمية VideoScribe.

المرجع المفكوك: shared/helpers/thinning.ts  (ZhangSuen + guo_hall)
عدد تكرارات Zhang-Suen يُستخدم عندهم لتقدير سماكة القلم (brushSize).
"""
from __future__ import annotations

import numpy as np

__all__ = ["zhang_suen", "guo_hall", "thin"]


def _neighbours(img: np.ndarray):
    """P2..P9 كما في الكود الأصلي (P2 شمال، ثم عكس عقارب الساعة)."""
    p = np.pad(img, 1, constant_values=False)
    P2 = p[:-2, 1:-1]   # N
    P3 = p[:-2, 2:]     # NE
    P4 = p[1:-1, 2:]    # E
    P5 = p[2:, 2:]      # SE
    P6 = p[2:, 1:-1]    # S
    P7 = p[2:, :-2]     # SW
    P8 = p[1:-1, :-2]   # W
    P9 = p[:-2, :-2]    # NW
    return P2, P3, P4, P5, P6, P7, P8, P9


def _u(*bools) -> np.ndarray:
    acc = bools[0].astype(np.uint8)
    for b in bools[1:]:
        acc = acc + b.astype(np.uint8)
    return acc


def zhang_suen(img: np.ndarray) -> tuple[np.ndarray, int]:
    """تخفيف Zhang-Suen. يعيد (الصورة المخففة، عدد التكرارات الكاملة)."""
    img = img.astype(bool).copy()
    iterations = 0
    while True:
        iterations += 1
        changed = 0
        for step in (1, 2):
            P2, P3, P4, P5, P6, P7, P8, P9 = _neighbours(img)
            B = _u(P2, P3, P4, P5, P6, P7, P8, P9)
            A = _u(~P2 & (P3 | P4), ~P4 & (P5 | P6), ~P6 & (P7 | P8), ~P8 & (P9 | P2))
            if step == 1:
                cond = (A == 1) & (B >= 2) & (B <= 6) & ~(P2 & P4 & P6) & ~(P4 & P6 & P8)
            else:
                cond = (A == 1) & (B >= 2) & (B <= 6) & ~(P2 & P4 & P8) & ~(P2 & P6 & P8)
            rem = cond & img
            n = int(rem.sum())
            if n:
                img[rem] = False
                changed += n
        if changed == 0:
            break
    return img, iterations


def _guo_hall_iteration(img: np.ndarray, odd: bool) -> int:
    P2, P3, P4, P5, P6, P7, P8, P9 = _neighbours(img)
    N1 = _u(P9 | P2, P3 | P4, P5 | P6, P7 | P8)
    N2 = _u(P2 | P3, P4 | P5, P6 | P7, P8 | P9)
    N = np.minimum(N1, N2)
    C = _u(~P2 & (P3 | P4), ~P4 & (P5 | P6), ~P6 & (P7 | P8), ~P8 & (P9 | P2))
    if odd:
        m = P8 & (P6 | P7 | ~P9)
    else:
        m = P4 & (P2 | P3 | ~P5)
    cond = (C == 1) & (N >= 2) & (N <= 3) & (~m)
    rem = cond & img
    n = int(rem.sum())
    if n:
        img[rem] = False
    return n


def guo_hall(img: np.ndarray, max_iter: int = 400) -> np.ndarray:
    """تخفيف Guo-Hall (يثبّت النهايات وينظف بعد Zhang-Suen)."""
    img = img.astype(bool).copy()
    it = 0
    while True:
        it += 1
        changed = _guo_hall_iteration(img, False) + _guo_hall_iteration(img, True)
        if changed == 0 or it >= max_iter:
            break
    return img


def _guo_hall_counted(img: np.ndarray, max_iter: int = 400) -> tuple[np.ndarray, int]:
    img = img.astype(bool).copy()
    it = 0
    while True:
        it += 1
        changed = _guo_hall_iteration(img, False) + _guo_hall_iteration(img, True)
        if changed == 0 or it >= max_iter:
            break
    return img, it


def thin(img: np.ndarray) -> tuple[np.ndarray, int]:
    """التخفيف إلى خط بعرض بكسل واحد — **Guo-Hall فقط**.

    ملاحظة Phase 3.1: تنفيذ Zhang-Suen القديم (المأخوذ من VideoScribe) كان
    يفتّت المنحنيات الرفيعة إلى شرطات منفصلة (قياس: حلقة 5px → 53 مكوّنًا)،
    وهذا هو الجذر الفعلي لـ«الحروف المتكتّلة/المفتّتة». Guo-Hall وحده يعطي
    هيكلًا متصلًا (حلقة 5px → مكوّن واحد) وهو خوارزمية تخفيف كاملة قائمة بذاتها.

    يعيد (الهيكل، عدد التكرارات) — التكرارات تُستخدم كتقدير تقريبي للسماكة فقط.
    """
    return _guo_hall_counted(img)
