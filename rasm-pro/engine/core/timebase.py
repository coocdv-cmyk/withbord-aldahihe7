"""قاعدة زمن دقيقة: إطارات/عينات بكسور عقلانية — بلا انزلاق وبلا أخطاء تراكمية.

المبدأ (PHASE 1): الزمن له مرجع واحد (عينات الصوت)، والرسم والتوقيت يُشتقّان منه.
كل التحويلات هنا بكسور عقلانية ``Fraction`` — لا floats في أي قرار حدودي:

- ``FrameRate``: كسر مثل 30000/1001 — يقبل معدلات NTSC بالضبط.
- ``SampleRate``: معدل عينات صحيح (44100/48000) وتحويلات دقيقة.
- ``map_boundaries_to_frames``: تعيين حدود كلمات/جمل (بالعينات المطلقة) إلى
  إطارات مطلقة — التعيين مطلق لا تراكمي، فلا ينزلق زمن الصوت عن الصورة أبدًا.
- ``Interval``: فترات نصف-مفتوحة [start, end) مع تحقق رتيب/تقاطع صريح.

أي إدخال غير صالح يرفع ``TimebaseError`` (نرفض بدلًا من التخمين).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Sequence

__all__ = [
    "TimebaseError",
    "FrameRate",
    "SampleRate",
    "Interval",
    "NTSC_24",
    "NTSC_30",
    "NTSC_60",
    "validate_intervals",
    "map_boundaries_to_frames",
]

_ROUND_MODES = ("floor", "round", "ceil")


class TimebaseError(ValueError):
    """خطأ في العقد الزمني — يُرفض بدل التخمين."""


def _round_fraction(f: Fraction, mode: str) -> int:
    if mode == "floor":
        return f.numerator // f.denominator
    if mode == "ceil":
        return -((-f.numerator) // f.denominator)
    if mode == "round":
        return (f + Fraction(1, 2)).numerator // (f + Fraction(1, 2)).denominator
    raise TimebaseError(f"نمط تقريب غير معروف: {mode!r} (المتاح: {_ROUND_MODES})")


@dataclass(frozen=True)
class FrameRate:
    """معدل إطارات ككسر عقلاني (مثال: 30000/1001 = 29.97)."""

    num: int
    den: int = 1

    def __post_init__(self) -> None:
        if self.num <= 0 or self.den <= 0:
            raise TimebaseError(f"معدل إطارات غير صالح: {self.num}/{self.den}")

    @property
    def value(self) -> Fraction:
        return Fraction(self.num, self.den)

    @property
    def fps(self) -> float:
        return self.num / self.den

    def __str__(self) -> str:
        return f"{self.num}/{self.den}"

    def frames_for_duration(self, seconds, *, mode: str = "round") -> int:
        """عدد الإطارات لمدة (ثانية كسرية مسموحة)."""
        return _round_fraction(Fraction(seconds) * self.value, mode)

    def time_of_frame(self, frame: int) -> Fraction:
        """وقت بداية الإطار (ثوانٍ ككسر)."""
        if frame < 0:
            raise TimebaseError(f"رقم إطار سالب: {frame}")
        return Fraction(frame * self.den, self.num)

    def frame_of_time(self, seconds, *, mode: str = "floor") -> int:
        """رقم الإطار الذي يحتوي لحظة زمنية (افتراضي: floor = إطار البداية)."""
        if Fraction(seconds) < 0:
            raise TimebaseError(f"زمن سالب: {seconds}")
        f = Fraction(seconds) * self.value
        return _round_fraction(f, mode)

    def frame_range(self, start, end) -> tuple[int, int]:
        """نصف-مفتوح [floor(start), ceil(end)) — لا يُفقد أي جزء من الفترة."""
        if Fraction(end) < Fraction(start):
            raise TimebaseError(f"فترة مقلوبة: {start} → {end}")
        s = self.frame_of_time(start, mode="floor")
        e = self.frame_of_time(end, mode="ceil")
        return s, max(e, s)


NTSC_24 = FrameRate(24000, 1001)
NTSC_30 = FrameRate(30000, 1001)
NTSC_60 = FrameRate(60000, 1001)


@dataclass(frozen=True)
class SampleRate:
    """معدل عينات الصوت (هرتز صحيح)."""

    hz: int

    def __post_init__(self) -> None:
        if self.hz <= 0:
            raise TimebaseError(f"معدل عينات غير صالح: {self.hz}")

    def samples_for_duration(self, seconds, *, mode: str = "round") -> int:
        """عدد العينات لمدة — بلا أي تحويل عشري."""
        return _round_fraction(Fraction(seconds) * self.hz, mode)

    def time_of_sample(self, index: int) -> Fraction:
        if index < 0:
            raise TimebaseError(f"رقم عينة سالب: {index}")
        return Fraction(index, self.hz)

    def samples_of_frame(self, frame: int, fps: FrameRate, *, mode: str = "floor") -> int:
        """عينة بداية إطار فيديو — تعيين مطلق (frame → samples)."""
        return self.samples_for_duration(fps.time_of_frame(frame), mode=mode)


@dataclass(frozen=True)
class Interval:
    """فترة نصف-مفتوحة [start, end) بوحدات العينات."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise TimebaseError(f"فترة سالبة: [{self.start}, {self.end})")
        if self.end < self.start:
            raise TimebaseError(f"فترة مقلوبة: [{self.start}, {self.end})")

    @property
    def length(self) -> int:
        return self.end - self.start

    def contains(self, sample: int) -> bool:
        return self.start <= sample < self.end


def validate_intervals(intervals: Sequence[Interval], *, total_samples: int | None = None) -> None:
    """يرفض: ترتيبًا مقلوبًا، تقاطعًا، أو خروجًا عن حدود الصوت."""
    prev: Interval | None = None
    for i, iv in enumerate(intervals):
        if total_samples is not None and iv.end > total_samples:
            raise TimebaseError(f"فترة رقم {i} تتجاوز الصوت: end={iv.end} > {total_samples}")
        if prev is not None and iv.start < prev.end:
            raise TimebaseError(f"تقاطع بين الفترتين {prev} و{iv}")
        prev = iv


def map_boundaries_to_frames(
    boundaries: Iterable[int],
    sample_rate: SampleRate,
    fps: FrameRate,
    *,
    total_samples: int | None = None,
    mode: str = "floor",
) -> list[int]:
    """حدود (عينات مطلقة) → إطارات (مطلقة) — مطلق لا تراكمي (لا انزلاق).

    - كل حد يُحوَّل باستقلال: frame = floor(b / hz * fps) — النتيجة لا تعتمد
      على الحدود السابقة إطلاقًا.
    - يرفض: حدود سالبة/خارج الصوت/غير مرتبة.
    """
    out: list[int] = []
    prev_b: int | None = None
    for b in boundaries:
        if b < 0:
            raise TimebaseError(f"حد سالب: {b}")
        if total_samples is not None and b > total_samples:
            raise TimebaseError(f"حد خارج الصوت: {b} > {total_samples}")
        if prev_b is not None and b < prev_b:
            raise TimebaseError(f"حدود غير مرتبة: {b} بعد {prev_b}")
        prev_b = b
        out.append(fps.frame_of_time(sample_rate.time_of_sample(b), mode=mode))
    return out
