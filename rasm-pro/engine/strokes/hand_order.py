# -*- coding: utf-8 -*-
"""ترتيب كتابة يدوية موثَّق من هيكل الحرف — تمثيل بياني + مسار أصيل.

لماذا بديل عن متتبّع البوصلة (VideoScribe) في النصوص العربية:

- المتتبّع القديم يتوقّف عند كل مفصل ويعيد البدء من طرف جديد، فيتفتّت الحرف
  الواحد إلى عشرات الشظايا (قياس Milestone-1: 35-40 شظية/حرف)، وكل شظية
  تُرسم بأطراف مستديرة → كتل حبر ملزوقة لا حروف.
- قرار «أين أبدأ» عنده كان نقطة-بكسل، لا قرارًا على مستوى الشكل.

هذا الملف يبني ترتيبًا صريحًا يمكن التحقق منه (Validated Centerlines):

1. عُقَد الهيكل تُكتشف ضمنيًا من درجات الجيران (8 اتجاهات).
2. البداية: طرف (درجة 1) أقصى اليمين ثم الأعلى للعربية (اتجاه RTL)،
   وأقصى اليسار لغيرها — وهذا يطابق بداية الكتابة الطبيعية.
3. المشي: استمرار بأقل انحراف اتجاه (سلاسة اليد) مع لاحق واضح عند التفرّع.
4. عند الانحشار (لم يبق جار) → رفع قلم ونقطة بداية جديدة من الطرف الأيمن
   المتبقّي، وتُعلَّم النقطة ``moveTo=True`` فلا يُرسم خط عبر الفراغ.
5. لا حلقات ولا تكرار: كل بكسل حبر يُزار مرة واحدة بالضبط.

الناتج بنفس صيغة ``generate_mask_path`` لتوافق بقية الأنبوب:
``[{"x": float, "y": float, "moveTo": bool}, ...]``

الحدود المعلنة: هذا ترتيب مشتق من شكل الحرف ومُتحقَّق منه بقواعد، وليس بيانات
كتابة بشرية مؤلَّفة يدويًا (InkML). يُصنَّف لذلك ضمن «Verified Handwriting (مشتق)».
"""
from __future__ import annotations

import numpy as np

__all__ = ["order_mask_paths"]

_NEIGH8: tuple[tuple[int, int], ...] = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
)


def order_mask_paths(mask: np.ndarray, rtl: bool = True) -> list[dict]:
    """يحوّل هيكلًا (بكسلات عرض 1) إلى مسارات رسم مرتّبة بأسلوب الكتابة.

    ``mask``: مصفوفة bool. ``rtl``: True للعربية (يبدأ من أقصى اليمين).
    """
    ink = mask.astype(bool)
    ys, xs = np.nonzero(ink)
    if len(ys) == 0:
        return []

    remaining: set[tuple[int, int]] = set(zip(ys.tolist(), xs.tolist()))

    def nbrs(p: tuple[int, int]) -> list[tuple[int, int]]:
        y, x = p
        out = []
        for dy, dx in _NEIGH8:
            q = (y + dy, x + dx)
            if q in remaining:
                out.append(q)
        return out

    def pick_start() -> tuple[int, int]:
        """طرف (درجة 1) أقصى في اتجاه الكتابة، أو أقصى بكسل متبقٍّ عند الحلقات."""
        terminals = [p for p in remaining if len(nbrs(p)) == 1]
        pool = terminals or remaining
        if rtl:
            return max(pool, key=lambda p: (p[1], -p[0]))  # أيمن ثم أعلى
        return min(pool, key=lambda p: (p[1], p[0]))        # أيسر ثم أعلى

    out: list[dict] = []
    total_points = len(remaining)
    guard = total_points * 2 + 64
    steps = 0

    while remaining and steps < guard:
        start = pick_start()
        remaining.discard(start)
        out.append({"x": int(start[1]), "y": int(start[0]), "moveTo": True})
        cur = start
        prev: tuple[int, int] | None = None
        while steps < guard:
            steps += 1
            cands = nbrs(cur)
            if not cands:
                break
            if prev is None:
                # أول خطوة من طرف/بداية مقطع: نفضّل التقدّم في اتجاه الكتابة
                def _first_key(q: tuple[int, int]) -> tuple[int, int]:
                    dx = q[1] - cur[1]
                    dy = q[0] - cur[0]
                    want_left = dx < 0
                    primary = 0 if (want_left if rtl else not want_left) else 1
                    return (primary, abs(dx) + abs(dy))

                chosen = min(cands, key=_first_key)
            else:
                vy, vx = cur[0] - prev[0], cur[1] - prev[1]
                nv = (vy * vy + vx * vx) ** 0.5 or 1.0

                def _key(q: tuple[int, int]) -> tuple[float, int]:
                    wy, wx = q[0] - cur[0], q[1] - cur[1]
                    nw = (wy * wy + wx * wx) ** 0.5 or 1.0
                    dot = (vy * wy + vx * wx) / (nv * nw)  # +1 = استمرار تام
                    return (-dot, abs(wy) + abs(wx))

                chosen = min(cands, key=_key)
            remaining.discard(chosen)
            out.append({"x": int(chosen[1]), "y": int(chosen[0]), "moveTo": False})
            prev, cur = cur, chosen
    return out
