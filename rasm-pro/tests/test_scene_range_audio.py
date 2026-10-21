"""Regression: a scene-range export starts the narration at that scene.

The renderer used to pass the whole narration to ffmpeg even when only scenes
N..M were exported, so every range preview/export began with the first scene's
audio.  This test uses one distinct tone per second and measures the exported
audio, not just the reported timestamps.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from engine.audio.loudness import decode_samples
from engine.render import Director
from engine.render.validate import validate_video

from conftest import requires_ffmpeg, requires_ffprobe

RATE = 16000
FREQS = (300.0, 600.0, 900.0)


def _tone_per_second(path: Path) -> Path:
    samples = []
    for freq in FREQS:
        for i in range(RATE):
            samples.append(int(12000 * math.sin(2 * math.pi * freq * i / RATE)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", v) for v in samples))
    return path


def _text(text: str) -> dict:
    return {
        "type": "text",
        "text": text,
        "font": "inter",
        "size": 48,
        "rect": [20, 20, 280, 100],
        "mode": "skeleton",
        "rtl": False,
        "color": "#211E1A",
        "gap": 0.2,
    }


def _plan() -> dict:
    return {
        "fps": {"num": 24, "den": 1},
        "canvas": [320, 180],
        "family": {"motion": {"zoom": 1.8, "follow": 0.07}},
        "scenes": [
            {
                "id": i + 1,
                "duration": 1.0,
                "start_frame": i * 24,
                "end_frame": (i + 1) * 24,
                "duration_frames": 24,
                "elements": [_text(label)],
            }
            for i, label in enumerate(("One", "Two", "Three"))
        ],
    }


def _dominant_frequency(samples: np.ndarray, rate: int) -> float:
    x = samples[0] if samples.ndim == 2 else samples
    x = x[int(0.10 * rate) : int(0.40 * rate)]
    if x.size == 0:
        return 0.0
    x = x * np.hanning(x.size)
    spectrum = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(x.size, 1.0 / rate)
    return float(freqs[int(np.argmax(spectrum))])


@requires_ffmpeg
@requires_ffprobe
def test_scene_range_export_seeks_the_narration(tmp_path: Path):
    audio = _tone_per_second(tmp_path / "narration.wav")
    out = tmp_path / "range.mp4"
    director = Director(_plan(), canvas=(320, 180), out_size=(160, 90))
    result = director.render(out, audio=audio, scene_range=(2, 3), strict=True)

    assert result["frames"] == 48
    assert result["audio_start_sec"] == pytest.approx(1.0)
    report = validate_video(
        out,
        expect_size=(160, 90),
        expect_fps={"num": 24, "den": 1},
        expect_frames=48,
        expect_audio=True,
        expect_duration_sec=result["duration_sec_exact"],
    )
    assert report["ok"], report["checks"]

    samples, rate = decode_samples(out)
    assert _dominant_frequency(samples, rate) == pytest.approx(600.0, rel=0.04)
    # The exported audio must cover scenes 2..3 only: 2 s, not 3 s.
    duration = samples.shape[1] / rate
    assert duration == pytest.approx(2.0, abs=0.08)
