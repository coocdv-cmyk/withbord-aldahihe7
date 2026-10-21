"""Regression: القوالب **مخططات** لا وصفات — المشاهد المتتالية لا تتشابه.

كان لكل دورٍ مخططٌ واحد: 18 مشهدًا متتاليًا = 18 لقطة شبه متطابقة، فأ_delegation
الصورة كانت تُرسم دائمًا يسارًا والتعليق دائمًا يمينًا.

الآن: لكل دورٍ عدة مخططات، والمشهدان المتتاليان لا يأخذان المخطط نفسه،
وكل مشهد يحمل اسم مخططه في ``layout``.
"""
from __future__ import annotations

from engine.stages.plan import LAYOUTS, VARIANTS, build_plan


def _research() -> dict:
    return {
        "entities": [
            {
                "name": "خريطة",
                "assets": [{"asset": {"path": "assets/map.svg", "mime": "image/svg+xml"}}],
            }
        ]
    }


def test_every_role_has_more_than_one_layout():
    for role, layouts in LAYOUTS.items():
        assert len(layouts) >= 2, role
    assert set(LAYOUTS) == {"hook", "evidence", "explain", "close"}


def test_two_consecutive_scenes_never_share_the_same_layout():
    scenes = [
        {"id": i, "duration": 8.0, "narration": f"Statement number {i} about the topic"}
        for i in range(1, 13)
    ]
    plan = build_plan(
        {"lang": "en", "hook": "Opening", "scenes": scenes}, _research()
    )
    layouts = [s.get("layout") for s in plan["scenes"]]
    assert all(layouts), layouts
    for a, b in zip(layouts, layouts[1:]):
        assert a != b, layouts


def test_the_picture_moves_between_the_sides_of_the_page():
    """A scene with a picture uses the evidence layout: the picture is drawn
    and the caption sits on the other side of it."""
    scenes = [
        {"id": 1, "duration": 8.0, "narration": "خريطة الطريق"},
        {"id": 2, "duration": 8.0, "narration": "خريطة الطريق"},
        {"id": 3, "duration": 8.0, "narration": "خريطة الطريق"},
        {"id": 4, "duration": 8.0, "narration": "خريطة الطريق"},
    ]
    plan = build_plan({"lang": "ar", "hook": "خريطة", "scenes": scenes}, _research())
    image_sides = set()
    for scene in plan["scenes"]:
        for element in scene["elements"]:
            if element.get("type") in ("image", "svg"):
                x, y, w, h = element["rect"]
                image_sides.add((x + w / 2) < 1280)
    assert len(image_sides) == 2, image_sides


def test_the_layout_geometry_never_leaves_the_canvas():
    for role, layouts in LAYOUTS.items():
        for name, layout in layouts.items():
            for key, rect in layout.items():
                x, y, w, h = rect
                assert x >= 0 and y >= 0, (role, name, key)
                assert x + w <= 2560, (role, name, key)
                assert y + h <= 1440, (role, name, key)
