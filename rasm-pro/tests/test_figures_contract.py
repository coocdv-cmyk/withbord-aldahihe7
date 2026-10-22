"""Regression: الشخصيات المرسومة (ستيك مان) تُرسم بالقلم وتتفاعل مع المعنى.

* كل وضعية تعطي مسارات **مختلفة** (لا نسخة واحدة مكرّرة).
* الشخصية داخل صندوقها تمامًا.
* **الوضعية تتبع معنى الجملة**: سؤال ⇒ تفكير، سبب ⇒ تركيز، ختام ⇒ ترحيب.
* الخطة تضع الشخصية في مشاهد الشرح والخاتمة، والدور يُرسم بصوت القلم.
"""
from __future__ import annotations

from engine.render.figures import (
    POSES,
    UNIT_H,
    UNIT_W,
    figure_bbox,
    figure_paths,
    figure_strokes,
)
from engine.stages.plan import _figure_pose, build_plan


def test_every_pose_draws_something_different():
    signatures = {}
    for pose in POSES:
        paths = figure_paths(pose)
        assert paths, pose
        assert all(len(p) >= 2 for p in paths), pose
        # the signature is the geometry itself, not the bounding box (two poses
        # may share a box and still be different drawings)
        signature = tuple(
            (round(p[0][0]), round(p[0][1]), round(p[-1][0]), round(p[-1][1]), len(p))
            for p in paths
        )
        signatures[pose] = signature
    assert len(set(signatures.values())) == len(POSES), list(signatures)


def test_a_figure_stays_inside_its_box():
    for pose in POSES:
        x0, y0, x1, y1 = figure_bbox(pose)
        assert x0 >= 0 and y0 >= 0, pose
        assert x1 <= UNIT_W and y1 <= UNIT_H, pose


def test_the_strokes_are_ready_for_the_pen():
    strokes = figure_strokes("think")
    assert strokes
    for stroke in strokes:
        assert len(stroke.points) == len(stroke.lengths)
        assert stroke.lengths[-1] > 0
        assert stroke.brush > 0


def test_the_pose_follows_the_meaning_of_the_line():
    assert _figure_pose("هل هذا صحيح؟", "explain") == "think"
    assert _figure_pose("لأن الذاكرة تتغير", "explain") == "focus"
    assert _figure_pose("اكتب ملاحظة", "explain") == "read"
    assert _figure_pose("ابدأ اليوم", "close") == "cheer"
    assert _figure_pose("جملة عادية", "explain") == "point"


def test_the_plan_places_a_character_in_the_explain_and_close_scenes():
    plan = build_plan(
        {
            "lang": "ar",
            "hook": "سؤال البداية",
            "scenes": [
                {"id": 1, "duration": 10.0, "narration": "سؤال البداية؟"},
                {"id": 2, "duration": 12.0, "narration": "لأن الذاكرة تحتاج تكرارًا موزعًا على أيام"},
                {"id": 3, "duration": 12.0, "narration": "اكتب ملاحظة واحدة فقط ثم راجعها غدًا"},
            ],
        },
        {},
        family="explainer",
    )
    roles = [s["role"] for s in plan["scenes"]]
    assert roles[1] == "explain", roles
    figures = [
        el
        for scene in plan["scenes"]
        for el in scene["elements"]
        if el.get("type") == "figure"
    ]
    assert figures, "the explain scene must carry a character"
    poses = {el["pose"] for el in figures}
    assert "focus" in poses or "read" in poses, poses
    for el in figures:
        x, y, w, h = el["rect"]
        assert 0 <= x and x + w <= 2560
        assert 0 <= y and y + h <= 1440
