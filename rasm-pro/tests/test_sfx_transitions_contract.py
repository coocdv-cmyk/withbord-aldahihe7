"""Regression: المؤثرات become «أقوى» بالقياس لا بالوصف.

* **انتقال بين المشاهد**: كل مشهد بعد الأول يُفتح بصوت قلب ورقة (من التسجيل
  الحقيقي نفسه) — فالإيقاع يسمع تبديل الصفحة.
* **الخفض التلقائي (ducking)**: حيث يتكلم الراوي تخفت أصوات الغرفة، وحيث
  يتوقف ترجع — وهذا يُقاس من السرد الحقيقي، لا مقدَّر.
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from engine.audio.sfx import DUCK_DEPTH_DB, SFX_TYPES, TRANSITION_TYPE, build_track


def _tone(path: Path, seconds: float, freq: float = 220.0, sr: int = 48000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    data = (0.2 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def _events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"events": events}), encoding="utf-8")


def test_a_scene_transition_has_its_own_sound_type():
    assert TRANSITION_TYPE in SFX_TYPES
    spec = SFX_TYPES[TRANSITION_TYPE]
    # it must come from a real recording, never from a synthetic fallback
    assert spec["source"].endswith(".wav")
    assert spec["kind"] == "paper"


def test_the_transition_event_is_built_into_the_track(tmp_path: Path):
    events = tmp_path / "scene.sfx.json"
    _events(
        events,
        [
            {"t": 0.0, "output_t": 0.0, "kind": "down", "el_type": "text"},
            {"t": 0.4, "output_t": 0.4, "kind": "up", "el_type": "text"},
            {"t": 2.0, "output_t": 2.0, "kind": "transition", "el_type": "scene"},
        ],
    )
    out = tmp_path / "track.wav"
    report = build_track(events, out, duration=4.0)
    assert report["counts_by_type"].get(TRANSITION_TYPE, 0) == 1
    assert out.exists()


def test_the_sound_track_steps_down_under_the_voice(tmp_path: Path):
    # a narration that is loud in the first half and silent in the second
    narration = tmp_path / "narration.wav"
    sr = 48000
    n = sr * 4
    t = np.arange(n) / sr
    data = np.where(t < 2.0, 0.2 * np.sin(2 * np.pi * 220 * t), 0.0)
    with wave.open(str(narration), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((data * 32767).astype("<i2").tobytes())

    events = tmp_path / "scene.sfx.json"
    _events(
        events,
        [
            {"t": 0.2, "output_t": 0.2, "kind": "down", "el_type": "text"},
            {"t": 0.6, "output_t": 0.6, "kind": "up", "el_type": "text"},
            {"t": 2.4, "output_t": 2.4, "kind": "down", "el_type": "text"},
            {"t": 2.8, "output_t": 2.8, "kind": "up", "el_type": "text"},
        ],
    )
    out = tmp_path / "track.wav"
    report = build_track(events, out, duration=4.0, narration=narration)
    duck = report["ducking"]
    assert duck["applied"] is True
    assert duck["depth_db"] == DUCK_DEPTH_DB
    assert 0.2 < duck["ducked_fraction"] < 0.8, duck

    with wave.open(str(out), "rb") as w:
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32)
    under = float(np.sqrt(np.mean(samples[int(0.2 * sr) : int(0.6 * sr)] ** 2)))
    alone = float(np.sqrt(np.mean(samples[int(2.4 * sr) : int(2.8 * sr)] ** 2)))
    assert under < alone, (under, alone)


def test_without_a_narration_nothing_is_ducked(tmp_path: Path):
    events = tmp_path / "scene.sfx.json"
    _events(events, [{"t": 0.2, "output_t": 0.2, "kind": "down", "el_type": "text"},
                     {"t": 0.6, "output_t": 0.6, "kind": "up", "el_type": "text"}])
    out = tmp_path / "track.wav"
    report = build_track(events, out, duration=2.0)
    assert report["ducking"]["applied"] is False
