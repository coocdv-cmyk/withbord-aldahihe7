"""Regression: an Arabic text element must never be drawn left-to-right.

The local-model audit (``local-model-audit/ARTIFACT-CHECKS.json``) found that
**all six** Arabic text elements of a language-model-written plan carried
``rtl=false`` — the film rendered Arabic left-to-right, i.e. reversed words.
The engine did not notice.  Now the plan validator refuses such a plan before
anything is rendered.

``rtl`` absent is not a defect: the text pipeline then decides the direction
from the first strong letter (``engine/strokes/text_paths.py``).
"""
from __future__ import annotations

from engine.stages.validate_plan import validate_plan


def _plan(text: str, rtl) -> dict:
    element = {
        "type": "text",
        "text": text,
        "font": "cairo",
        "size": 120,
        "rect": [130, 380, 2300, 700],
        "mode": "skeleton",
        "color": "#211E1A",
    }
    if rtl is not None:
        element["rtl"] = rtl
    return {
        "fps": {"num": 24, "den": 1},
        "canvas": [2560, 1440],
        "lang": "ar",
        "scenes": [
            {
                "id": 1,
                "duration": 6.0,
                "start_frame": 0,
                "end_frame": 144,
                "duration_frames": 144,
                "elements": [element],
            }
        ],
    }


def test_arabic_text_with_rtl_false_is_refused():
    report = validate_plan(_plan("الذاكرة لا تحتفظ بكل شيء", False))
    assert report["ok"] is False
    assert any("rtl=false" in error for error in report["errors"]), report["errors"]


def test_arabic_text_with_rtl_true_is_accepted():
    report = validate_plan(_plan("الذاكرة لا تحتفظ بكل شيء", True))
    assert report["ok"] is True, report["errors"]


def test_arabic_text_without_an_explicit_direction_is_accepted():
    # absent == auto (the text pipeline decides from the first strong letter)
    report = validate_plan(_plan("الذاكرة لا تحتفظ بكل شيء", None))
    assert report["ok"] is True, report["errors"]


def test_english_text_with_rtl_false_stays_valid():
    report = validate_plan(_plan("A line about memory that keeps what we see", False))
    assert report["ok"] is True, report["errors"]
