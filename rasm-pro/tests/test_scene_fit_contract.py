"""Regression: a scene must finish inside its own time, or be refused.

The renderer used to report ``overflow`` after it had already opened the output
file.  A production render now has to refuse *before* writing anything when a
required element cannot be placed inside the scene, and it must say which
element is missing instead of silently dropping it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.render import Director
from engine.render.director import RenderPreflightError


def _scene(scene_id: int, duration_frames: int, elements: list[dict]) -> dict:
    return {
        "id": scene_id,
        "duration": duration_frames / 24,
        "start_frame": 0,
        "end_frame": duration_frames,
        "duration_frames": duration_frames,
        "elements": elements,
    }


def _text(text: str = "A short line") -> dict:
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


def _plan(scene: dict) -> dict:
    return {
        "fps": {"num": 24, "den": 1},
        "canvas": [320, 180],
        "family": {"motion": {"zoom": 1.8, "follow": 0.07}},
        "scenes": [scene],
    }


def test_decor_elements_cannot_be_forced_into_too_short_a_scene():
    scene = _scene(
        1,
        24,
        [
            {"type": "paper_card", "rect": [20, 20, 200, 120], "reveal_time": 0.5, "gap": 0.2}
            for _ in range(4)
        ],
    )
    director = Director(_plan(scene), canvas=(320, 180), out_size=(160, 90))
    items, natural, scale = director._prepare_scene(scene, 1.0)
    end = max(item["start"] + item["dur"] for item in items)
    assert natural > 1.0
    assert scale > 1.0
    # The minimum per element still cannot fit: this is exactly the case the
    # old "overflow" flag reported only after the file was already created.
    assert end > 1.0


def test_preflight_refuses_an_impossible_scene_before_the_output_exists(tmp_path: Path):
    scene = _scene(
        1,
        24,
        [
            {"type": "paper_card", "rect": [20, 20, 200, 120], "reveal_time": 0.5, "gap": 0.2}
            for _ in range(4)
        ],
    )
    out = tmp_path / "must-not-exist.mp4"
    director = Director(_plan(scene), canvas=(320, 180), out_size=(160, 90))
    report = director.preflight()
    assert report["ok"] is False
    assert report["blocking"]
    assert report["blocking"][0]["reason"] == "scene-does-not-fit"

    with pytest.raises(RenderPreflightError) as excinfo:
        director.render(out, strict=True)
    assert "scene-does-not-fit" in str(excinfo.value)
    assert not out.exists()


def test_preflight_reports_a_missing_required_element(tmp_path: Path):
    scene = _scene(
        1,
        48,
        [
            _text(),
            {
                "type": "image",
                "asset": str(tmp_path / "missing.png"),
                "rect": [20, 20, 200, 120],
            },
        ],
    )
    director = Director(_plan(scene), canvas=(320, 180), out_size=(160, 90))
    report = director.preflight()
    assert report["ok"] is False
    reasons = {item["reason"] for item in report["blocking"]}
    assert "element-missing" in reasons
    assert report["scenes"][0]["missing_elements"] == 1


def test_a_fitting_scene_passes_preflight():
    scene = _scene(1, 96, [_text("One line")])
    director = Director(_plan(scene), canvas=(320, 180), out_size=(160, 90))
    report = director.preflight()
    assert report["ok"] is True, report["blocking"]
    assert report["scenes"][0]["fits"] is True


def test_a_compressible_scene_is_reported_compressed_not_overflow(tmp_path: Path):
    """Natural drawing may exceed the scene only when the result still fits.

    The old report called every speed-up an ``overflow`` even though the
    strokes were compressed inside the scene.  That made a successful render
    look like a broken deliverable.  ``overflow`` is now the post-fit result;
    a speed-up is reported separately as ``compressed`` with its factor.
    """
    scene = _scene(
        1,
        48,
        [_text("A line that needs a little more than two seconds to draw")],
    )
    out = tmp_path / "compressed.mp4"
    director = Director(_plan(scene), canvas=(320, 180), out_size=(160, 90))
    report = director.preflight()
    assert report["ok"] is True, report["blocking"]
    assert report["scenes"][0]["fits"] is True
    assert report["scenes"][0]["natural_seconds"] > report["scenes"][0]["planned_seconds"]
    assert report["scenes"][0]["time_scale"] > 1.0

    result = director.render(out, strict=True)
    assert out.exists()
    assert result["overflow_scenes"] == []
    assert result["compressed_scenes"] == [1]
    rendered = result["scenes"][0]
    assert rendered["overflow"] is False
    assert rendered["compressed"] is True
    assert rendered["drawn_end_seconds"] <= rendered["source_seconds"] + 1e-6
