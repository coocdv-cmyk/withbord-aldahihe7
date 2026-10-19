"""Tests for studio <-> rasm-pro bridge."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import rasm_bridge


def test_bridge_available():
    assert rasm_bridge.RASM_AVAILABLE is True


def test_understand_and_plan_roundtrip():
    td = Path(tempfile.mkdtemp())
    try:
        script = "In 1914 war began. Soldiers fought. Peace came in 1919."
        r = rasm_bridge.understand_script(script, "t_proj", offline=True)
        assert r["graph"]["stats"]["scenes"] >= 1
        import_narr = None
        # build plan without audio
        plan = rasm_bridge.build_plan_studio("t_proj")
        assert plan["stats"]["scenes"] >= 1
        proj = rasm_bridge.rasm_to_studio_project(plan, "12345678901234567890123456789012")
        assert len(proj["scenes"]) == plan["stats"]["scenes"]
        for s in proj["scenes"]:
            assert s["duration"] > 0
    finally:
        shutil.rmtree(td, ignore_errors=True)


def test_timing_monotonic():
    # Use rasm timebase directly via bridge module import
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rasm-pro"))
    from engine.core.timebase import FrameRate, SampleRate, map_boundaries_to_frames
    from fractions import Fraction
    sr = SampleRate(48000)
    fps = FrameRate(30000, 1001)
    bounds = [i * 48000 for i in range(0, 101)]
    frames = map_boundaries_to_frames(bounds, sr, fps)
    assert len(frames) == len(bounds)
    assert all(a <= b for a, b in zip(frames, frames[1:]))
    # no drift: absolute mapping
    for b, fr in zip(bounds, frames):
        assert fr == fps.frame_of_time(sr.time_of_sample(b), mode="floor")
