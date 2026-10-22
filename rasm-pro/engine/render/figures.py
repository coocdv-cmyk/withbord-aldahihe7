"""الشخصيات المرسومة (ستيك مان) — تُرسم بالقلم مثل كل شيء آخر.

لماذا في المحرك: الفيديو يجب أن يوصل **بصريًّا** قبل أن يوصل صوتيًّا.
شخصية تفكّر أو تشير أو تقرأ تنقل معنى الجملة بلا صوت.

كل شخصية **متجهية** (parametric): رأس ودقن وجسم وأطراف، تتغيّر بالوضعية
(إشارة، تفكير، تركيز، قراءة، ترحيب، إعجاب،idle). لا صور خارجية ولا أصول
مرخّصة: هي strokes يولّدها المحرك ويرسمها القلم.

الإحداثي: نظام محلي 0..1000 (عرض) و0..1400 (ارتفاع)، يُوسَّع إلى المستطيل.
"""

from __future__ import annotations

import math
import random
from typing import Iterable

POSES = (
    "idle",
    "point",
    "wave",
    "think",
    "focus",
    "read",
    "cheer",
    "like",
)

# عرض وارتفاع النظام المحلي
UNIT_W = 1000.0
UNIT_H = 1400.0


def _circle(cx: float, cy: float, r: float, steps: int = 26) -> list[list[float]]:
    return [
        [cx + r * math.cos(2 * math.pi * i / steps), cy + r * math.sin(2 * math.pi * i / steps)]
        for i in range(steps + 1)
    ]


def _line(a: tuple[float, float], b: tuple[float, float]) -> list[list[float]]:
    return [[a[0], a[1]], [b[0], b[1]]]


def _poly(points: Iterable[tuple[float, float]]) -> list[list[float]]:
    return [[x, y] for x, y in points]


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, steps: int = 12) -> list[list[float]]:
    out = []
    for i in range(steps + 1):
        a = a0 + (a1 - a0) * i / steps
        out.append([cx + r * math.cos(a), cy + r * math.sin(a)])
    return out


def figure_paths(pose: str = "idle", *, seed: int = 7) -> list[list[list[float]]]:
    """مسارات شخصية واحدة (كل مسار قائمة نقاط) في النظام المحلي."""
    pose = pose if pose in POSES else "idle"
    rng = random.Random(seed + sum(ord(c) for c in pose))
    wobble = lambda: rng.uniform(-6.0, 6.0)  # noqa: E731 — a hand-drawn wobble

    head_cx, head_cy, head_r = 500.0, 250.0, 130.0
    neck = (head_cx, head_cy + head_r)
    hip = (head_cx + wobble(), 720.0)
    shoulder_l = (head_cx - 95, 430)
    shoulder_r = (head_cx + 95, 430)

    paths: list[list[list[float]]] = []
    paths.append(_circle(head_cx, head_cy, head_r))
    # the face: two eyes and a mouth (a smile, a frown, or a flat line)
    eye_dx, eye_dy, eye_r = 46.0, -20.0, 15.0
    paths.append(_circle(head_cx - eye_dx, head_cy + eye_dy, eye_r))
    paths.append(_circle(head_cx + eye_dx, head_cy + eye_dy, eye_r))
    mouth = {
        "idle": (0.35, 0.55),
        "point": (0.25, 0.5),
        "wave": (0.3, 0.6),
        "think": (0.1, 0.35),
        "focus": (0.05, 0.3),
        "read": (0.15, 0.4),
        "cheer": (0.45, 0.75),
        "like": (0.4, 0.7),
    }[pose]
    paths.append(
        _arc(head_cx, head_cy + 55.0, 62.0, mouth[0] * math.pi, mouth[1] * math.pi)
    )
    # the body and the legs
    paths.append(_line(neck, hip))
    paths.append(_line(hip, (hip[0] - 95, 1180)))
    paths.append(_line(hip, (hip[0] + 95, 1180)))
    paths.append(_line((hip[0] - 130, 1200), (hip[0] - 60, 1200)))
    paths.append(_line((hip[0] + 60, 1200), (hip[0] + 130, 1200)))

    if pose == "point":
        paths.append(_line(shoulder_r, (head_cx + 330, 470)))
        paths.append(_line((head_cx + 330, 470), (head_cx + 430, 440)))
        paths.append(_line(shoulder_l, (head_cx - 170, 640)))
    elif pose == "wave":
        paths.append(_line(shoulder_r, (head_cx + 300, 300)))
        paths.append(_line((head_cx + 300, 300), (head_cx + 360, 170)))
        paths.append(_line((head_cx + 360, 170), (head_cx + 300, 90)))
        paths.append(_line(shoulder_l, (head_cx - 160, 620)))
    elif pose == "think":
        paths.append(_line(shoulder_r, (head_cx + 200, 520)))
        paths.append(_line((head_cx + 200, 520), (head_cx + 120, 380)))
        paths.append(_line((head_cx + 120, 380), (head_cx + 190, 330)))
        paths.append(_line(shoulder_l, (head_cx - 170, 600)))
        # a thought bubble
        paths.append(_circle(head_cx + 250, 150, 46))
        paths.append(_circle(head_cx + 330, 80, 28))
    elif pose == "focus":
        paths.append(_line(shoulder_r, (head_cx + 250, 560)))
        paths.append(_line((head_cx + 250, 560), (head_cx + 120, 620)))
        paths.append(_line(shoulder_l, (head_cx - 150, 560)))
        # a magnifier
        paths.append(_circle(head_cx + 250, 470, 70))
        paths.append(_line((head_cx + 300, 520), (head_cx + 380, 600)))
    elif pose == "read":
        paths.append(_line(shoulder_r, (head_cx + 160, 600)))
        paths.append(_line(shoulder_l, (head_cx - 160, 600)))
        paths.append(_line((head_cx - 170, 610), (head_cx + 170, 610)))
        paths.append(_line((head_cx, 545), (head_cx, 610)))
        paths.append(_line((head_cx - 150, 585), (head_cx + 150, 585)))
    elif pose == "cheer":
        paths.append(_line(shoulder_r, (head_cx + 280, 250)))
        paths.append(_line(shoulder_l, (head_cx - 280, 250)))
        paths.append(_line((hip[0] - 95, 1180), (hip[0] - 40, 1180)))
        paths.append(_line((hip[0] + 95, 1180), (hip[0] + 40, 1180)))
    elif pose == "like":
        paths.append(_line(shoulder_r, (head_cx + 200, 560)))
        paths.append(_line((head_cx + 200, 560), (head_cx + 90, 500)))
        paths.append(_line(shoulder_l, (head_cx - 170, 600)))
        # a heart
        heart = []
        for i in range(25):
            t = 2 * math.pi * i / 24
            hx = 16 * math.sin(t) ** 3
            hy = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            heart.append([head_cx + 250 + hx * 5.0, 220 - hy * 5.0])
        paths.append(heart)
    else:  # idle
        paths.append(_line(shoulder_r, (head_cx + 170, 650)))
        paths.append(_line(shoulder_l, (head_cx - 170, 650)))
    return paths


def figure_strokes(pose: str = "idle", *, brush: float = 9.0, seed: int = 7, color: str | None = None):
    """المسارات جاهزة للرسم (نفس نوع مسارات المحرك)."""
    from ..strokes.model import Stroke

    out: list[Stroke] = []
    for points in figure_paths(pose, seed=seed):
        if len(points) < 2:
            continue
        lengths = [0.0]
        for i in range(1, len(points)):
            lengths.append(
                lengths[-1] + math.dist(points[i - 1], points[i])
            )
        out.append(
            Stroke(
                points=points,
                lengths=lengths,
                brush=brush,
                kind="draw",
                color=color,
                brush_profile=[brush] * len(points),
                jumps=None,
                meta={"figure": pose},
            )
        )
    return out


def figure_bbox(pose: str = "idle", *, seed: int = 7) -> tuple[float, float, float, float]:
    """صندوق الشخصية في النظام المحلي."""
    xs: list[float] = []
    ys: list[float] = []
    for points in figure_paths(pose, seed=seed):
        for x, y in points:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (0.0, 0.0, UNIT_W, UNIT_H)
    return (min(xs), min(ys), max(xs), max(ys))
