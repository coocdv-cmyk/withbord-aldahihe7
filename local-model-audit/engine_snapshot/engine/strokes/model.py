"""موديل مسارات الرسم (.rstrokes.json) — العقد بين مصنع الأصول ومحرك الرسم."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..core.paths import CACHE
from ..core.util import read_json, sha256_text, write_json

ENGINE_VERSION = "rasm-strokes/1.0"


@dataclass
class Stroke:
    points: list[list[float]]                 # [[x, y], ...] بوحدات الأصل
    lengths: list[float]                      # طول تراكمي عند كل نقطة
    brush: float                              # سماكة القلم الأساسية (نصف القطر)
    kind: str = "draw"                        # draw | fill | glyph
    color: str | None = None                  # يملؤها الستايل لاحقًا
    brush_profile: list[float] | None = None  # نصف قطر لكل نقطة (اختياري — جودة أعلى)
    jumps: list[int] | None = None            # مؤشرات بدايات المسارات الفرعية (رفع القلم)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def total_length(self) -> float:
        return self.lengths[-1] if self.lengths else 0.0

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)

    def start(self) -> list[float]:
        return self.points[0] if self.points else [0.0, 0.0]

    def end(self) -> list[float]:
        return self.points[-1] if self.points else [0.0, 0.0]


def _rdp_mask(points: list[list[float]], tol: float) -> list[int]:
    """Douglas-Peucker — يعيد مؤشرات النقاط المحفوظة."""
    n = len(points)
    if n < 3:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        x0, y0 = points[i0]
        x1, y1 = points[i1]
        dx, dy = x1 - x0, y1 - y0
        norm = math.hypot(dx, dy)
        best_i, best_d = -1, -1.0
        for i in range(i0 + 1, i1):
            px, py = points[i]
            if norm == 0:
                d = math.hypot(px - x0, py - y0)
            else:
                d = abs(dy * px - dx * py + x1 * y0 - y1 * x0) / norm
            if d > best_d:
                best_i, best_d = i, d
        if best_d > tol:
            keep[best_i] = True
            stack.append((i0, best_i))
            stack.append((best_i, i1))
    return [i for i, k in enumerate(keep) if k]


def simplify_stroke(stroke: Stroke, tol: float = 0.6) -> Stroke:
    """تبسيط المسار مع الحفاظ على الشكل وإعادة حساب الأطوال."""
    if len(stroke.points) < 3 or tol <= 0:
        return stroke
    idx = _rdp_mask(stroke.points, tol)
    pts = [stroke.points[i] for i in idx]
    lengths: list[float] = []
    total = 0.0
    for i, p in enumerate(pts):
        if i == 0:
            lengths.append(0.0)
            continue
        q = pts[i - 1]
        total += math.dist(p, q)
        lengths.append(total)
    profile = [stroke.brush_profile[i] for i in idx] if stroke.brush_profile else None
    jump_set = set(stroke.jumps or [])
    jumps = [new_i for new_i, old_i in enumerate(idx) if old_i in jump_set]
    return Stroke(points=pts, lengths=lengths, brush=stroke.brush, kind=stroke.kind, color=stroke.color,
                  brush_profile=profile, jumps=jumps or None, meta=stroke.meta)


@dataclass
class StrokeDoc:
    asset: str
    source: str                               # svg | raster | text | generated
    width: float
    height: float
    strokes: list[Stroke]
    view_box: list[float] | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    engine: str = ENGINE_VERSION

    def total_length(self) -> float:
        return sum(s.total_length for s in self.strokes)

    def save(self, path: str | Path) -> Path:
        data = {
            "engine": self.engine,
            "asset": self.asset,
            "source": self.source,
            "width": self.width,
            "height": self.height,
            "view_box": self.view_box,
            "stats": self.stats,
            "strokes": [asdict(s) for s in self.strokes],
        }
        return write_json(path, data, indent=None)

    @classmethod
    def load(cls, path: str | Path) -> "StrokeDoc":
        data = read_json(path)
        strokes = [Stroke(**s) for s in data.get("strokes", [])]
        return cls(
            asset=data.get("asset", ""),
            source=data.get("source", ""),
            width=data.get("width", 0),
            height=data.get("height", 0),
            view_box=data.get("view_box"),
            stats=data.get("stats", {}),
            strokes=strokes,
            engine=data.get("engine", ENGINE_VERSION),
        )


def stroke_cache_path(key: str) -> Path:
    """مسار كاش ثابت لكل أصل/خيارات (بلا تكرار أعمال)."""
    h = sha256_text(key)[:24]
    p = CACHE / "strokes" / f"{h}.rstrokes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
