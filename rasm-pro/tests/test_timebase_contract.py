from __future__ import annotations

from fractions import Fraction

import pytest

from engine.audio.sfx import _events_from_json
from engine.core.plan_time import plan_frame_rate, scene_frame_bounds
from engine.core.timebase import FrameRate, TimebaseError
from engine.render import Director


def test_long_plan_uses_absolute_boundaries_without_drift():
    plan = {
        "fps": {"num": 24, "den": 1},
        "scenes": [
            {"id": 1, "duration": 600.1},
            {"id": 2, "duration": 599.9},
            {"id": 3, "duration": 600.0},
        ],
    }
    bounds = scene_frame_bounds(plan)
    assert [b["frames"] for b in bounds] == [14402, 14398, 14400]
    assert bounds[-1]["end_frame"] == 43200
    assert bounds[1]["start_frame"] == bounds[0]["end_frame"]
    assert bounds[2]["start_frame"] == bounds[1]["end_frame"]


def test_ntsc_long_plan_is_exact_at_frame_boundaries():
    fps = {"num": 30000, "den": 1001}
    plan = {
        "fps": fps,
        "scenes": [
            {"id": 1, "duration": 600.1},
            {"id": 2, "duration": 599.9},
            {"id": 3, "duration": 600.0},
        ],
    }
    bounds = scene_frame_bounds(plan)
    expected = FrameRate(30000, 1001).frame_of_time(Fraction(1800), mode="round")
    assert bounds[-1]["end_frame"] == expected
    assert sum(b["frames"] for b in bounds) == expected


def test_audio_samples_are_mapped_once():
    plan = {
        "fps": {"num": 24, "den": 1},
        "audio": {"sample_rate": 48000, "total_samples": 96000},
        "scenes": [
            {"id": 1, "start_sample": 0, "end_sample": 48000, "duration_frames": 24},
            {"id": 2, "start_sample": 48000, "end_sample": 96000, "duration_frames": 24},
        ],
    }
    bounds = scene_frame_bounds(plan)
    assert [(b["start_frame"], b["end_frame"]) for b in bounds] == [(0, 24), (24, 48)]
    with pytest.raises(TimebaseError):
        scene_frame_bounds(
            {
                **plan,
                "scenes": [
                    {"id": 1, "start_sample": 0, "end_sample": 40000},
                    {"id": 2, "start_sample": 48000, "end_sample": 96000},
                ],
            }
        )
    with pytest.raises(TimebaseError):
        scene_frame_bounds(
            {
                **plan,
                "audio": {"sample_rate": 48000, "total_samples": 120000},
            }
        )


def test_director_rejects_silent_rate_change():
    plan = {"fps": 30, "scenes": [{"id": 1, "duration": 1.0, "elements": []}]}
    with pytest.raises(TimebaseError):
        Director(plan, fps=24)
    assert Director(plan, fps=None).fps_rate == FrameRate(30)


def test_legacy_numeric_rate_is_normalized():
    assert plan_frame_rate({"fps": 24}) == FrameRate(24)
    assert plan_frame_rate({"fps": "30000/1001"}) == FrameRate(30000, 1001)


def test_sfx_prefers_output_clock(tmp_path):
    p = tmp_path / "sfx.json"
    p.write_text(
        '{"events":[{"t":100.0,"output_t":0.5,"kind":"down","x":1,"y":2,"stroke":0}]}',
        encoding="utf-8",
    )
    data = _events_from_json(p)
    event = data["events"][0]
    assert event["t"] == 0.5
    assert event["project_t"] == 100.0
