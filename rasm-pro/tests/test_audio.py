"""اختبارات الصوت: فحص دقيق، استيراد بلا تعديل الأصل، محاذاة صريحة، تحقق تصدير حقيقي."""
from __future__ import annotations

import math
import struct
import tempfile
import wave
from fractions import Fraction
from pathlib import Path

from engine.audio import (
    AudioError,
    alignment_frames,
    baseline_align,
    import_narration,
    load_alignment,
    load_narration,
    probe_audio,
    save_alignment,
    sha256_file,
)
from engine.core.timebase import FrameRate
from engine.render.video import FFmpegWriter
from engine.render.validate import validate_video


def _make_wav(path: Path, seconds: float, rate: int = 16000, freq: float = 440.0) -> Path:
    n = int(round(seconds * rate))
    buf = bytearray()
    for i in range(n):
        v = int(12000 * math.sin(2 * math.pi * freq * i / rate))
        buf += struct.pack("<h", v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(buf))
    return path


def test_probe_exact_samples_and_duration():
    with tempfile.TemporaryDirectory() as td:
        p = _make_wav(Path(td) / "a.wav", 2.5, rate=16000)
        d = probe_audio(p)
        assert d["sample_rate"] == 16000
        assert d["channels"] == 1
        assert d["total_samples"] == 40000, d["total_samples"]
        assert Fraction(d["duration_exact"]) == Fraction(5, 2)
        assert abs(d["duration_sec"] - 2.5) < 1e-6
        assert len(d["peaks_max"]) >= 20
        assert all(-1.0 <= v <= 1.0 for v in d["peaks_max"])


def test_sha256_stable_and_streaming():
    with tempfile.TemporaryDirectory() as td:
        p1 = _make_wav(Path(td) / "a.wav", 2.0, rate=8000)
        p2 = _make_wav(Path(td) / "b.wav", 2.0, rate=8000, freq=220.0)
        h1 = sha256_file(p1)
        assert h1 == sha256_file(p1)
        assert h1 != sha256_file(p2)
        assert len(h1) == 64


def test_import_narration_never_modifies_original_and_reuses():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = _make_wav(root / "src.wav", 3.0, rate=16000)
        h_before = sha256_file(src)
        st_before = src.stat()

        proj = root / "proj"
        m1 = import_narration(proj, src, note="اختبار")
        assert Path(m1["path"]).exists()
        assert m1["sha256"] == h_before
        assert src.stat().st_size == st_before.st_size
        assert sha256_file(src) == h_before
        assert m1["total_samples"] == 48000

        # الاستيراد الثاني: نفس الملف بلا تكرار
        m2 = import_narration(proj, src)
        assert m2["path"] == m1["path"]
        copies = list((proj / "audio").glob("narration-*"))
        assert len(copies) == 1, [c.name for c in copies]

        loaded = load_narration(proj)
        assert loaded and loaded["sha256"] == h_before


def test_import_rejects_missing_file():
    with tempfile.TemporaryDirectory() as td:
        try:
            import_narration(Path(td) / "p", Path(td) / "nope.wav")
        except AudioError:
            return
    raise AssertionError("متوقع رفض ملف غير موجود")


def test_baseline_align_exact_and_contiguous():
    scenes = [
        {"id": 1, "narration": "في صيف عام 1914 اشتعلت الحرب العالمية الأولى بعد اغتيال ولي عهد النمسا."},
        {"id": 2, "narration": "حفر الجنود الخنادق على الجبهة الغربية في معركة السوم."},
        {"id": 3, "narration": "وقعت ألمانيا معاهدة فرساي في يونيو 1919."},
    ]
    total = 441_000  # 10 ثوانٍ @ 44100
    al = baseline_align(scenes, total, 44100)
    assert al.level == "APPROXIMATE"
    assert al.segments[0].start_sample == 0
    assert al.segments[-1].end_sample == total
    assert sum(s.length for s in al.segments) == total
    for a, b in zip(al.segments, al.segments[1:]):
        assert a.end_sample == b.start_sample
        assert a.length > 0
    assert all(0.1 <= s.confidence <= 0.5 for s in al.segments)

    # محاذاة مستحيلة: نص ضخم في صوت قصير → علم معدل غير معقول
    al2 = baseline_align(
        [{"id": 1, "narration": "كلمة " * 4000}], 44100, 44100
    )
    assert any("rate-implausible" in s.flags for s in al2.segments)
    assert any("غير معقول" in n for n in al2.notes)


def test_alignment_frames_contiguous_and_absolute():
    al = baseline_align(
        [
            {"id": 1, "narration": "الجملة الأولى هنا."},
            {"id": 2, "narration": "الجملة الثانية أطول قليلًا من الأولى."},
            {"id": 3, "narration": "الثالثة."},
        ],
        48000,
        48000,
    )
    fr = alignment_frames(al, fps=FrameRate(30))
    assert len(fr) == 3
    assert fr[0]["start_frame"] == 0
    for a, b in zip(fr, fr[1:]):
        assert a["end_frame"] == b["start_frame"]
    assert fr[-1]["end_frame"] <= 30  # ثانية واحدة @30fps → ≤ 30 إطار


def test_alignment_roundtrip_disk():
    with tempfile.TemporaryDirectory() as td:
        al = baseline_align([{"id": 5, "narration": "نص تجريبي."}], 16000, 16000)
        save_alignment(al, td)
        back = load_alignment(td)
        assert back is not None
        assert back.level == al.level
        assert [s.scene_id for s in back.segments] == [5]
        assert back.segments[0].start_sample == 0
        assert back.segments[0].end_sample == 16000


def test_validate_video_real_export():
    from PIL import Image

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        wav = _make_wav(root / "n.wav", 1.0, rate=16000)
        out = root / "v.mp4"
        w = FFmpegWriter(out, (160, 120), fps=15, crf=30, preset="ultrafast", audio=wav)
        img = Image.new("RGB", (160, 120), (240, 236, 225))
        for i in range(15):
            w.write(img)
        w.close()
        assert out.exists() and out.stat().st_size > 0

        rep = validate_video(
            out,
            expect_size=(160, 120),
            expect_fps=15,
            expect_audio=True,
            expect_duration_sec=1.0,
            tolerance_frames=2,
        )
        assert rep["ok"], rep
        names = {c["check"] for c in rep["checks"]}
        assert {"exists", "video-stream", "size", "fps", "duration", "audio-present"} <= names

        bad = validate_video(out, expect_size=(320, 240), expect_fps=30, expect_audio=False)
        assert not bad["ok"]
        failed = {c["check"] for c in bad["checks"] if not c["ok"]}
        assert {"size", "fps", "audio-present"} <= failed
