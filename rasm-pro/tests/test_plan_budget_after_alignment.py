"""The text budget is stated for the scene duration that will be rendered.

The plan used to compute ``text_budget`` from the estimated words-per-second
duration and only then replace scene times with measured alignment.  A scene
that became twice as long (or half as long) kept a budget for a duration it no
longer had, so `rasm plan --check` could approve a scene the renderer cannot
draw — or reject one that is comfortable.
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

from engine.stages.plan import build_plan


def _empty_wav(path: Path, seconds: float, rate: int = 8000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))


def test_budget_uses_alignment_durations_not_estimates(tmp_path: Path):
    pd = tmp_path / "project"
    (pd / "audio").mkdir(parents=True)
    _empty_wav(pd / "audio" / "narration.wav", 6.0, 1000)
    rate = 1000
    start = 0
    segments = []
    for scene_id, seconds in ((1, 5.0), (2, 1.0)):
        end = start + int(seconds * rate)
        segments.append(
            {
                "scene_id": scene_id,
                "text": f"نص المشهد {scene_id}",
                "start_sample": start,
                "end_sample": end,
                "confidence": 0.8,
                "flags": [],
            }
        )
        start = end
    (pd / "audio" / "narration.json").write_text(
        json.dumps(
            {
                "version": 2,
                "path": "audio/narration.wav",
                "stored": {"path": "audio/narration.wav", "name": "narration.wav", "copied": True},
                "sha256": "0" * 64,
                "codec": "pcm_s16le",
                "sample_rate": rate,
                "channels": 1,
                "total_samples": start,
                "duration_sec": 6.0,
                "duration_exact": "6",
                "loudness": {"lufs_integrated": -16.0, "duration_sec": 6.0},
            }
        ),
        encoding="utf-8",
    )
    (pd / "audio" / "alignment.json").write_text(
        json.dumps(
            {
                "version": 1,
                "level": "MEASURED",
                "method": "test",
                "sample_rate": rate,
                "total_samples": start,
                "segments": segments,
                "notes": [],
            }
        ),
        encoding="utf-8",
    )
    graph = {
        "lang": "ar",
        "hook": "عنوان",
        "scenes": [
            {"id": 1, "narration": "نص المشهد 1", "duration": 6.0},
            {"id": 2, "narration": "نص المشهد 2", "duration": 6.0},
        ],
    }
    plan = build_plan(graph, {}, project_dir=pd, fps=24)
    durations = [scene["duration"] for scene in plan["scenes"]]
    assert durations == [5.0, 1.0]
    assert plan["scenes"][0]["text_budget"]["capacity_words"] == int(5.0 * 0.95)
    assert plan["scenes"][1]["text_budget"]["capacity_words"] == int(1.0 * 0.95)
    assert plan["scenes"][1]["text_budget"]["fits"] is False
    assert plan["stats"]["scenes_over_text_budget"] >= 1
