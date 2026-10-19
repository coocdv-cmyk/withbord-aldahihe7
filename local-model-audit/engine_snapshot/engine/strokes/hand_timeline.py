"""زمن الكتابة اليدوية: آلة حالات القلم + إيقاع طبيعي + أحداث صوت.

الحالات: INIT → TRAVEL(القلم مرفوع يتحرك) → PEN_DOWN → DRAW → PEN_UP →
(وقفة كلمة/ترقيم) → TRAVEL … → COMPLETE.

النموذج:
- المسار يُقسَم إلى «قطع» = المسافات الفرعية بين قفزتين متتاليتين (رفع القلم
  الحقيقي للنقاط/الوصلات المقطوعة).
- لكل قطعة: انتقال بزمن حقيقي من نهاية القطعة السابقة (سريع لكن ليس فوريًا)،
  ثم رسم بمنحنى نعومة (smoothstep) يعطي تسارعًا وتباطؤًا طبيعيًا، ثم وقفة قصيرة
  (تطول عند نهاية كلمة/ترقيم).
- advance(frac) يحوّل نسبة [0,1] (التي يمرّرها المخرج) إلى أجزاء رسم جديدة،
  وtip() يعيد موضع القلم في كل الحالات (بما فيها الانتقال المرفوع) فيبدو
  الانتقال طبيعيًا بدل القفز.
- events: عناوين زمنية (down/up/tap/complete) لاستخدامها في مؤثرات الصوت.

وحدة مستقلة عن اللوحة (own arc-length walker) — بلا دورات استيراد.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .model import Stroke

TRAVEL_PPS = 1400.0      # بكسل/ث للانتقال المرفوع (اللوحة المنطقية)
DRAW_PPS = 420.0         # سرعة الكتابة المرجعية (النسبة بين الاثنين هي المهمة)
MIN_TAP_SEC = 0.05       # أقصر ملامسة (نقرة نقطة إعجام)
PAUSE_IN_PIECE = 0.012   # بين قطع الحبر المتصلة داخل الكلمة
PAUSE_WORD = 0.06        # وقفة خفيفة بعد الكلمة
PAUSE_PUNCT = 0.11       # وقفة أوضح بعد الترقيم
TRAVEL_MIN = 0.03
TRAVEL_MAX = 0.55
INITIAL_DELAY = 0.06


def _ease(p: float) -> float:
    """smoothstep: تسارع ثم تباطؤ (إحساس يد حقيقية)."""
    p = min(max(p, 0.0), 1.0)
    return p * p * (3.0 - 2.0 * p)


def _cumulative(points: list[list[float]]) -> list[float]:
    lens: list[float] = []
    total = 0.0
    for i, p in enumerate(points):
        if i:
            total += math.dist(p, points[i - 1])
        lens.append(total)
    return lens


class _Walker:
    """يمشي على مسار واحد ويعيد الأجزاء الجديدة فقط (يتخطى قفزات رفع القلم)."""

    __slots__ = ("pts", "lens", "jumps", "seg_i", "seg_t", "tip_xy", "prof", "brush")

    def __init__(self, stroke: Stroke):
        self.pts = stroke.points
        self.lens = stroke.lengths or _cumulative(stroke.points)
        self.jumps = set(stroke.jumps or [])
        self.seg_i = 0
        self.seg_t = 0.0
        self.tip_xy: tuple[float, float] | None = None
        self.prof = stroke.brush_profile
        self.brush = stroke.brush

    def advance(self, upto: float) -> list[tuple[float, float, float, float, float]]:
        out: list[tuple[float, float, float, float, float]] = []
        pts, lens = self.pts, self.lens
        n = len(pts)
        while self.seg_i < n - 1:
            i = self.seg_i
            if (i + 1) in self.jumps:  # رفع قلم: لا رسم بين النقطتين
                self.seg_i += 1
                self.seg_t = 0.0
                continue
            seg_start, seg_end = lens[i], lens[i + 1]
            if upto <= seg_start:
                break
            t0 = self.seg_t
            t1 = 1.0 if upto >= seg_end else (upto - seg_start) / max(seg_end - seg_start, 1e-9)
            if t1 <= t0:
                break
            x0 = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t0
            y0 = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t0
            x1 = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t1
            y1 = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t1
            if self.prof and i + 1 < len(self.prof):
                r = max(0.6, 0.5 * (self.prof[i] + self.prof[i + 1]))
            else:
                r = max(0.6, self.brush)
            out.append((x0, y0, x1, y1, r))
            self.tip_xy = (x1, y1)
            if upto >= seg_end:
                self.seg_i += 1
                self.seg_t = 0.0
            else:
                self.seg_t = t1
                break
        return out

    @property
    def done(self) -> bool:
        return self.seg_i >= len(self.pts) - 1


@dataclass
class PenEvent:
    t: float             # زمن محلي طبيعي (ثواني)
    kind: str            # down | up | tap | complete
    x: float
    y: float
    stroke: int = -1
    word: int | None = None


@dataclass
class _Piece:
    si: int
    L0: float
    L1: float
    start_xy: tuple[float, float]
    end_xy: tuple[float, float]
    travel_from: tuple[float, float] | None
    t_travel0: float = 0.0
    t_travel1: float = 0.0
    t_draw0: float = 0.0
    t_draw1: float = 0.0
    pause_after: float = PAUSE_IN_PIECE
    tap: bool = False


class HandTimeline:
    """خط زمن رسم يدوي لمسار واحد أو مستند كامل."""

    def __init__(
        self,
        strokes: list[Stroke],
        *,
        words: list[dict] | None = None,
        travel_pps: float = TRAVEL_PPS,
        draw_pps: float = DRAW_PPS,
        ease: bool = True,
    ):
        self.strokes = strokes
        self.walkers = [_Walker(s) for s in strokes]
        self.ease = bool(ease)
        self.pieces: list[_Piece] = []
        self.events: list[PenEvent] = []
        self._t = 0.0

        w_of: dict[int, int] = {}
        word_punct: dict[int, bool] = {}
        if words:
            for wi, w in enumerate(words):
                for si in range(int(w.get("start", 0)), int(w.get("end", 0))):
                    w_of[si] = wi
                word_punct[wi] = bool(w.get("punct"))

        t = 0.0
        prev_end: tuple[float, float] | None = None
        for si, st in enumerate(strokes):
            pts = st.points
            lens = st.lengths or _cumulative(pts)
            n = len(pts)
            if n < 2:
                continue
            jumps = set(st.jumps or [])
            starts = [0] + sorted(j for j in jumps if 0 < j < n)
            for k, i0 in enumerate(starts):
                i1 = (starts[k + 1] - 1) if k + 1 < len(starts) else (n - 1)
                if i1 <= i0:
                    continue
                L0, L1 = float(lens[i0]), float(lens[i1])
                piece_len = max(L1 - L0, 0.0)
                pc = _Piece(
                    si=si, L0=L0, L1=L1,
                    start_xy=(pts[i0][0], pts[i0][1]),
                    end_xy=(pts[i1][0], pts[i1][1]),
                    travel_from=prev_end,
                )
                if prev_end is None:
                    pc.t_travel0 = pc.t_travel1 = 0.0
                    pc.t_draw0 = t + INITIAL_DELAY
                else:
                    d = math.dist(prev_end, pc.start_xy)
                    trav = min(max(d / max(travel_pps, 1.0), TRAVEL_MIN), TRAVEL_MAX)
                    pc.t_travel0 = t
                    pc.t_travel1 = t + trav
                    pc.t_draw0 = pc.t_travel1
                pc.tap = piece_len < 1.0
                dur = max(piece_len / max(draw_pps, 1.0), MIN_TAP_SEC if pc.tap else 0.02)
                pc.t_draw1 = pc.t_draw0 + dur
                # وقفة بعد آخر قطعة من الكلمة (بين الكلمات/الترقيم أطول)
                if k + 1 < len(starts):
                    pc.pause_after = PAUSE_IN_PIECE
                else:
                    wi = w_of.get(si)
                    nxt = w_of.get(si + 1)
                    if wi is not None and nxt != wi:
                        pc.pause_after = PAUSE_PUNCT if word_punct.get(wi) else PAUSE_WORD
                    else:
                        pc.pause_after = PAUSE_IN_PIECE
                t = pc.t_draw1 + pc.pause_after
                self.pieces.append(pc)
                prev_end = pc.end_xy

        self.natural = max(t, 0.2)

        # أحداث القلم (زمن محلي طبيعي)
        for pi, pc in enumerate(self.pieces):
            if pc.tap:
                self.events.append(PenEvent(pc.t_draw0, "tap", pc.start_xy[0], pc.start_xy[1], pc.si))
            else:
                self.events.append(PenEvent(pc.t_draw0, "down", pc.start_xy[0], pc.start_xy[1], pc.si))
                self.events.append(PenEvent(pc.t_draw1, "up", pc.end_xy[0], pc.end_xy[1], pc.si))
        self.events.append(PenEvent(self.natural, "complete",
                                    self.pieces[-1].end_xy[0] if self.pieces else 0.0,
                                    self.pieces[-1].end_xy[1] if self.pieces else 0.0))
        self.events.sort(key=lambda e: e.t)

    # ---------- السحب الزمني ----------
    def wall_for_speed(self, px_per_sec: float) -> float:
        """المدة اللازمة لرسم هذا المستند بسرعة px/ث (تحافظ على نسبة الإيقاع)."""
        return self.natural * (DRAW_PPS / max(px_per_sec, 1.0))

    def advance(self, frac: float) -> list[tuple[float, float, float, float, float]]:
        """أجزاء الرسم الجديدة حتى النسبة frac من الزمن الطبيعي (تراكمي، رتيب)."""
        t = min(max(float(frac), 0.0), 1.0) * self.natural
        self._t = max(self._t, t)
        t = self._t
        out: list[tuple[float, float, float, float, float]] = []
        for pc in self.pieces:
            if t <= pc.t_draw0:
                break
            dur = max(pc.t_draw1 - pc.t_draw0, 1e-6)
            p = min(1.0, (t - pc.t_draw0) / dur)
            pe = _ease(p) if self.ease else p
            target = pc.L0 + (pc.L1 - pc.L0) * pe
            segs = self.walkers[pc.si].advance(target)
            if segs:
                out.extend(segs)
        return out

    def events_between(self, a: float, b: float) -> list[PenEvent]:
        """أحداث في نافذة زمنية طبيعية (a, b]."""
        return [e for e in self.events if a < e.t <= b]

    def tip(self) -> tuple[float, float] | None:
        """موضع القلم الحالي (خلال الرسم أو الانتقال المرفوع أو الوقفة)."""
        if not self.pieces:
            return None
        t = self._t
        for k, pc in enumerate(self.pieces):
            if t < pc.t_travel0:
                return self.pieces[k - 1].end_xy if k > 0 else pc.start_xy
            if t < pc.t_travel1:
                sd = max(pc.t_travel1 - pc.t_travel0, 1e-6)
                p = _ease((t - pc.t_travel0) / sd) if self.ease else (t - pc.t_travel0) / sd
                fx, fy = pc.travel_from or pc.start_xy
                return (fx + (pc.start_xy[0] - fx) * p, fy + (pc.start_xy[1] - fy) * p)
            if t < pc.t_draw1:
                cur = self.walkers[pc.si]
                return cur.tip_xy or pc.start_xy
            if t < pc.t_draw1 + pc.pause_after:
                return pc.end_xy
        return self.pieces[-1].end_xy

    @property
    def done(self) -> bool:
        return self._t >= self.natural and all(w.done for w in self.walkers)
