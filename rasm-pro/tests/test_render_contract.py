from __future__ import annotations

import json
import math
import struct
import wave
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image

from engine.render import Director
from engine.render.validate import validate_video
from engine.render.video import FFmpegWriter

from conftest import requires_ffmpeg


def _plan() -> dict:
    return {
        "fps": {"num": 24, "den": 1},
        "canvas": [640, 360],
        "scenes": [
            {
                "id": 1,
                "duration": 0.5,
                "start_frame": 0,
                "end_frame": 12,
                "duration_frames": 12,
                "elements": [
                    {
                        "type": "text",
                        "text": "Hello",
                        "font": "inter",
                        "size": 64,
                        "rect": [40, 80, 560, 160],
                        "mode": "skeleton",
                        "rtl": False,
                        "color": "#211E1A",
                        "gap": 0.2,
                    }
                ],
            }
        ],
        "stats": {"scenes": 1, "elements": 1, "duration": 0.5},
    }


@requires_ffmpeg
def test_director_render_is_frame_exact_and_events_have_absolute_clock(tmp_path):
    out = tmp_path / "out.mp4"
    res = Director(_plan(), canvas=(640, 360), out_size=(160, 90)).render(out)
    assert res["frames"] == 12
    assert res["expected_frames"] == 12
    assert res["drift_frames"] == 0
    assert res["seconds"] == 0.5
    assert res["fps"] == {"num": 24, "den": 1}
    assert res["scenes"][0]["frames"] == 12
    assert (tmp_path / "out.sfx.json").exists()
    sfx = json.loads((tmp_path / "out.sfx.json").read_text(encoding="utf-8"))
    assert sfx["fps_rate"] == {"num": 24, "den": 1}
    assert sfx["events"]
    for event in sfx["events"]:
        assert 0 <= event["frame"] <= 12
        assert 0.0 <= event["output_t"] <= 0.5
        assert event["output_frame"] in range(12)
    report = validate_video(
        out,
        expect_size=(160, 90),
        expect_fps={"num": 24, "den": 1},
        expect_frames=12,
        expect_audio=False,
        expect_duration_sec=Fraction(1, 2),
    )
    assert report["ok"], report["checks"]


def test_missing_ffmpeg_is_an_explicit_error(tmp_path):
    with pytest.raises(RuntimeError, match="ffmpeg"):
        FFmpegWriter(
            tmp_path / "missing.mp4",
            (16, 16),
            fps=24,
            ffmpeg=str(tmp_path / "does-not-exist.exe"),
            expected_frames=1,
        )


@requires_ffmpeg
def test_preview_keeps_source_scene_timing_not_compresses_it(tmp_path):
    plan = _plan()
    plan["scenes"][0].update(duration=1.0, end_frame=24, duration_frames=24)
    out = tmp_path / "preview.mp4"
    res = Director(plan, canvas=(640, 360), out_size=(160, 90)).render(
        out, max_seconds=0.75
    )
    scene = res["scenes"][0]
    assert scene["frames"] == 18
    assert scene["source_frames"] == 24
    assert scene["seconds"] == 0.75
    assert scene["source_seconds"] == 1.0
    sfx = json.loads((tmp_path / "preview.sfx.json").read_text(encoding="utf-8"))
    assert sfx["frames"] == 18
    assert all(0.0 <= e["output_t"] <= 0.75 for e in sfx["events"])
    assert sfx["events"]


def _make_wav(path: Path, seconds: float, rate: int = 16000) -> Path:
    n = int(round(seconds * rate))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            v = int(1200 * math.sin(2 * math.pi * 440 * i / rate))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))
    return path


@requires_ffmpeg
def test_writer_does_not_shortest_trim_video_when_audio_is_shorter(tmp_path):
    wav = _make_wav(tmp_path / "short.wav", 0.5)
    out = tmp_path / "mismatch.mp4"
    writer = FFmpegWriter(
        out, (64, 64), fps=24, audio=wav, expected_frames=24, preset="ultrafast"
    )
    for _ in range(24):
        writer.write(Image.new("RGB", (64, 64), (240, 240, 240)))
    writer.close()
    report = validate_video(
        out,
        expect_size=(64, 64),
        expect_fps=24,
        expect_frames=24,
        expect_audio=True,
        expect_duration_sec=Fraction(1, 1),
    )
    assert report["video"]["frames"] == 24
    assert any(c["check"] == "frames" and c["ok"] for c in report["checks"])
    assert any(
        c["check"] == "audio-video-duration" and not c["ok"] for c in report["checks"]
    )


@requires_ffmpeg
def test_ntsc_writer_keeps_rational_rate(tmp_path):
    out = tmp_path / "ntsc.mp4"
    writer = FFmpegWriter(
        out, (32, 32), fps="30000/1001", expected_frames=10, preset="ultrafast"
    )
    for _ in range(10):
        writer.write(Image.new("RGB", (32, 32), (0, 0, 0)))
    writer.close()
    report = validate_video(
        out,
        expect_size=(32, 32),
        expect_fps={"num": 30000, "den": 1001},
        expect_frames=10,
        expect_audio=False,
    )
    assert report["ok"], report["checks"]
