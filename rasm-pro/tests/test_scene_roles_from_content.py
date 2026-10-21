"""Regression: دور المشهد يُشتقّ من **محتواه** لا من رقمه.

القاعدة القديمة (1=hook، كل ثالث=explain، الأخير=close) كانت تُسقط الصورة
على مشهد `explain` — وهو دور بلا خانة صورة — فكان على المحرّر أن يعيد
ترتيب السكريبت يدويًا ليصيب الصورُ مشاهدها.

الآن: دور صريح من السكريبت يسبق الاستنتاج، ومشهد فيه **دليل مصوَّر** هو
`evidence`، والخاتمة التي تدعو للفعل `close`، وما عدا ذلك `explain`.
"""
from __future__ import annotations

from engine.stages.families import resolve_roles
from engine.stages.plan import build_plan


def _scene(text: str, role: str | None = None) -> dict:
    out = {"id": 0, "duration": 8.0, "narration": text}
    if role:
        out["role"] = role
    return out


def test_a_scene_with_a_picture_is_evidence():
    scenes = [
        _scene("Opening statement"),
        _scene("A claim with a source"),
        _scene("Another claim"),
        _scene("A closing thought"),
    ]
    roles = resolve_roles(scenes, has_visual=[False, True, False, False])
    assert roles[1] == "evidence", roles
    assert roles[2] == "explain", roles
    assert roles[0] == "hook", roles


def test_the_number_of_the_scene_does_not_decide_its_role():
    scenes = [_scene(f"Statement number {i}") for i in range(1, 8)]
    roles = resolve_roles(scenes, has_visual=[False, False, False, True, False, False, False])
    # the fourth scene (index 3) is not "explain" because 3 % 3 == 0
    assert roles[3] == "evidence", roles
    assert roles[5] == "explain", roles


def test_an_explicit_role_in_the_script_wins():
    scenes = [_scene("Opening"), _scene("Middle"), _scene("End")]
    scenes[1]["role"] = "explain"
    roles = resolve_roles(scenes, has_visual=[False, True, False])
    assert roles[1] == "explain", roles


def test_a_closing_call_to_action_is_a_close():
    scenes = [_scene("Opening"), _scene("Middle"), _scene("Start today with one page")]
    roles = resolve_roles(scenes, has_visual=[False, False, False])
    assert roles[2] == "close", roles


def test_a_closing_scene_with_a_picture_stays_evidence():
    scenes = [_scene("Opening"), _scene("Middle"), _scene("A final picture")]
    roles = resolve_roles(scenes, has_visual=[False, False, True])
    assert roles[2] == "evidence", roles


def test_the_plan_uses_the_resolved_roles():
    plan = build_plan(
        {
            "lang": "en",
            "hook": "The Art of War",
            "scenes": [
                {"id": 1, "duration": 8.0, "narration": "The Art of War"},
                {"id": 2, "duration": 8.0, "narration": "The Warring States period"},
                {"id": 3, "duration": 8.0, "narration": "The Warring States period"},
                {"id": 4, "duration": 8.0, "narration": "A closing thought"},
            ],
        },
        {
            "entities": [
                {
                    "name": "Warring States period",
                    "assets": [
                        {"asset": {"path": "assets/map.svg", "mime": "image/svg+xml"}}
                    ],
                }
            ]
        },
    )
    roles = [s["role"] for s in plan["scenes"]]
    assert roles[1] == "evidence", roles
    assert roles[2] == "evidence", roles
    # the picture is actually drawn in the scene that got the evidence role
    assert any(
        el.get("type") in ("image", "svg") for el in plan["scenes"][1]["elements"]
    )
