"""Regression: فحص التركيب يَرى ما يُرسم، لا ما هو مكتوب في الجدول.

* النصوص التي لا تسع صندوقها **تُصغَّر** عند الرندر (لا تُقصّ) — فالسؤال
  الصحيح: كم صارت صغيرة، وهل بلغت حدّ القراءة.
* العناصر التي تركب فوق بعضها تُرى في الفيديو لا في التقرير.
* المشهدان المتتاليان بنفس الشكل = «شريط كاذب» يخدع المشاهد.
"""
from __future__ import annotations

from engine.render.validate_composition import validate_composition


def _plan(elements, *, second_elements=None) -> dict:
    scenes = [
        {
            "id": 1,
            "role": "evidence",
            "layout": "a",
            "duration": 8.0,
            "elements": elements,
        }
    ]
    if second_elements is not None:
        scenes.append(
            {
                "id": 2,
                "role": "evidence",
                "layout": "a",
                "duration": 8.0,
                "elements": second_elements,
            }
        )
    return {"fps": {"num": 24, "den": 1}, "canvas": [2560, 1440], "scenes": scenes}


def _text(text: str, rect, size: int = 140) -> dict:
    return {
        "type": "text",
        "text": text,
        "font": "cairo",
        "size": size,
        "rect": list(rect),
        "mode": "skeleton",
        "rtl": False,
    }


def test_a_picture_under_the_text_is_refused():
    plan = _plan(
        [
            _text("A line of text here", [130, 380, 1200, 400]),
            {"type": "image", "asset": "assets/a.jpg", "rect": [130, 380, 1200, 400]},
        ]
    )
    report = validate_composition(plan)
    assert report["ok"] is False
    assert any(f["kind"] == "element-overlap" for f in report["blocking"])


def test_text_that_is_scaled_into_nothing_is_refused():
    plan = _plan([_text("A very long sentence that cannot possibly fit", [130, 380, 120, 90], 140)])
    report = validate_composition(plan)
    assert report["ok"] is False
    assert any(f["kind"] == "text-too-small" for f in report["blocking"])


def test_two_identical_scenes_in_a_row_are_flagged():
    elements = [_text("Same text", [130, 380, 1200, 400])]
    plan = _plan(elements, second_elements=list(elements))
    report = validate_composition(plan)
    assert report["ok"] is True  # a warning, not a refusal
    assert any(f["kind"] == "repeated-scene" for f in report["warnings"])


def test_a_clean_scene_passes():
    plan = _plan(
        [
            _text("A line of text here", [130, 380, 1200, 400]),
            {"type": "image", "asset": "assets/a.jpg", "rect": [1500, 380, 900, 600]},
        ]
    )
    report = validate_composition(plan)
    assert report["ok"] is True, report["blocking"]
    assert report["blocking"] == []
