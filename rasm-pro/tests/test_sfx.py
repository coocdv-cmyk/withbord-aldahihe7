from __future__ import annotations

import json
import wave
from pathlib import Path

from engine.audio.sfx import SR, build_track


def test_sfx_clamps_events_and_closes_open_strokes(tmp_path: Path):
    sfx = {
        "fps": 24,
        "scenes": [{"id": 1, "start": 0.0}, {"id": 2, "start": 1.0}, {"id": 3, "start": 9.0}],
        "events": [
            {"t": 0.10, "kind": "down"},
            {"t": 0.40, "kind": "up"},
            {"t": 0.50, "kind": "tap"},
            {"t": 1.90, "kind": "down"},
            {"t": 9.00, "kind": "tap"},
            {"t": -1.0, "kind": "tap"},
        ],
    }
    p = tmp_path / "events.sfx.json"
    p.write_text(json.dumps(sfx), encoding="utf-8")
    wav = tmp_path / "out.wav"
    info = build_track(p, wav, duration=2.0)
    assert info["requested_duration"] == 2.0
    assert info["dropped_events"] == 2
    assert info["closed_open_strokes"] == 1
    assert info["scratches"] == 2
    assert info["taps"] == 1
    assert info["slides"] == 1
    assert wav.exists()
    with wave.open(str(wav), "rb") as w:
        assert w.getframerate() == SR
        assert w.getnframes() == int(2.0 * SR) + SR // 2
