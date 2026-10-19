"""اختبارات قاعدة الزمن: دقة كسرية، NTSC، حدود، انزلاق، فترات — بلا pytest."""
from __future__ import annotations

from fractions import Fraction

from engine.core.timebase import (
    NTSC_24,
    NTSC_30,
    NTSC_60,
    FrameRate,
    Interval,
    SampleRate,
    TimebaseError,
    map_boundaries_to_frames,
    validate_intervals,
)

F = Fraction


def _raises(fn, exc=TimebaseError):
    try:
        fn()
    except exc:
        return True
    raise AssertionError(f"متوقع رفع {exc.__name__} — لم يُرفع")


def test_exact_30fps():
    fps = FrameRate(30)
    assert fps.frames_for_duration(10) == 300
    assert fps.time_of_frame(300) == F(10)
    assert fps.frame_of_time(F(10, 3)) == 100
    assert fps.frame_of_time(F(10, 3), mode="ceil") == 100
    assert fps.frame_of_time(F(1, 90), mode="ceil") == 1
    assert fps.frame_of_time(F(1, 90), mode="floor") == 0


def test_ntsc_rational_exact():
    # 30000/1001: قيمة مضبوطة بالكسر — لا float
    one_hour = NTSC_30.frames_for_duration(3600, mode="floor")
    assert one_hour == 107892, one_hour
    exact = F(3600) * NTSC_30.value
    assert exact == F(108000000, 1001)
    assert NTSC_30.time_of_frame(one_hour) == F(107892 * 1001, 30000)
    assert NTSC_30.time_of_frame(one_hour) < 3600
    # round-trip: أي إطار → زمن → نفس الإطار
    for n in (0, 1, 2, 1001, 30000, 107892, 215784):
        assert NTSC_30.frame_of_time(NTSC_30.time_of_frame(n), mode="floor") == n


def test_no_drift_long_durations():
    # المبدأ: الحساب المطلق = الكسر الدقيق (لا ينزلق)، والتراكم التقريبي ينزلق فعلًا.
    for minutes in (10, 60, 120):
        secs = minutes * 60
        exact_f = F(secs) * NTSC_30.value
        assert NTSC_30.frames_for_duration(secs, mode="floor") == exact_f.numerator // exact_f.denominator
        expected = NTSC_30.frames_for_duration(secs, mode="round")
        # التراكم (تقريب كل دقيقة ثم الضرب) ينزلق — نوثّق الفرق، لا نخفيه:
        per_min = NTSC_30.frames_for_duration(60)
        naive = per_min * minutes
        drift = abs(naive - expected)
        assert drift > 0, (minutes, naive, expected)  # التقريب التراكمي منحرف أصلًا
        # والحل المطلق يحصر الزمن الحقيقي: t(n) ≤ secs < t(n+1)
        n_floor = NTSC_30.frames_for_duration(secs, mode="floor")
        assert NTSC_30.time_of_frame(n_floor) <= secs < NTSC_30.time_of_frame(n_floor + 1)


def test_all_common_rates():
    for fps in (FrameRate(24), FrameRate(25), NTSC_24, FrameRate(30), NTSC_30, FrameRate(50), NTSC_60):
        n = fps.frames_for_duration(60)
        t = fps.time_of_frame(n)
        assert fps.frame_of_time(t, mode="floor") == n
        assert t >= F(0)


def test_sample_rate_exact():
    sr = SampleRate(48000)
    assert sr.samples_for_duration(1) == 48000
    assert sr.samples_for_duration(F(1, 1000)) == 48  # 1ms = 48 عينة
    assert sr.time_of_sample(48000) == F(1)
    # 1601.6 → floor 1601 · round 1602 · ceil 1602
    f1 = NTSC_30.time_of_frame(1)
    assert sr.samples_for_duration(f1, mode="floor") == 1601
    assert sr.samples_for_duration(f1, mode="round") == 1602
    assert sr.samples_for_duration(f1, mode="ceil") == 1602
    assert sr.samples_of_frame(1, NTSC_30, mode="floor") == 1601


def test_round_half_up():
    sr = SampleRate(2)
    assert sr.samples_for_duration(F(1, 4)) == 1  # 0.5 → 1 (نصف لأعلى)


def test_boundaries_absolute_no_drift():
    sr = SampleRate(48000)
    # كل ثانية لمدة 120 دقيقة = 7201 حدًا
    bounds = [i * 48000 for i in range(0, 7201)]
    frames = map_boundaries_to_frames(bounds, sr, NTSC_30)
    assert len(frames) == len(bounds)
    # مطلق: كل حد يطابق حسابًا مباشرًا مستقلًا
    for b, fr in list(zip(bounds, frames))[::997]:
        assert fr == NTSC_30.frame_of_time(sr.time_of_sample(b), mode="floor")
    # رتابة صارمة (غير متناقصة) وبلا انزلاق
    assert all(a <= b for a, b in zip(frames, frames[1:]))


def test_boundaries_many_and_rejects():
    sr = SampleRate(44100)
    many = [i * 441 for i in range(0, 100_000)]  # 100 ألف حد على 16.6 دقيقة
    out = map_boundaries_to_frames(many, sr, FrameRate(30))
    assert len(out) == 100_000
    assert all(a <= b for a, b in zip(out, out[1:]))
    _raises(lambda: map_boundaries_to_frames([100, 50], sr, FrameRate(30)))
    _raises(lambda: map_boundaries_to_frames([-1], sr, FrameRate(30)))
    _raises(lambda: map_boundaries_to_frames([1000], sr, FrameRate(30), total_samples=999))


def test_frame_range_half_open():
    fps = FrameRate(30)
    s, e = fps.frame_range(0, F(1, 30))
    assert (s, e) == (0, 1)
    s, e = fps.frame_range(F(1, 90), F(2, 90))
    assert fps.time_of_frame(s) <= F(1, 90)
    assert fps.time_of_frame(e) >= F(2, 90)
    _raises(lambda: fps.frame_range(2, 1))


def test_intervals_validation():
    ivs = [Interval(0, 100), Interval(100, 250), Interval(250, 250)]
    validate_intervals(ivs, total_samples=300)
    _raises(lambda: validate_intervals([Interval(0, 100), Interval(99, 200)]))
    _raises(lambda: validate_intervals([Interval(0, 100)], total_samples=99))
    _raises(lambda: Interval(200, 100))
    _raises(lambda: Interval(-5, 10))


def test_invalid_rates_rejected():
    _raises(lambda: FrameRate(0))
    _raises(lambda: FrameRate(-30))
    _raises(lambda: FrameRate(30, 0))
    _raises(lambda: SampleRate(0))
    _raises(lambda: SampleRate(-48000))
    _raises(lambda: FrameRate(30).frames_for_duration(1, mode="nearest"))
