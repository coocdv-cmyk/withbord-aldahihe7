"""Stage 6 contract: template families, motion rules and the measured draw budget."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.core.plan_time import scene_frame_bounds
from engine.render import Director
from engine.stages.families import FAMILIES, SCENE_ROLES, get_family, scene_role
from engine.stages.plan import (
    MAX_NARRATION_WORDS_PER_SECOND,
    NATURAL_DRAWN_WORDS_PER_SECOND,
    build_plan,
)
from engine.stages.validate_plan import validate_plan


def _graph(lang: str = "en", scenes: int = 4) -> dict:
    bodies = {
        "en": [
            "In the summer of 1914 the world went to war.",
            "The Somme in 1916 was months of trench fighting.",
            "The United States entered the war in 1917.",
            "The Treaty of Versailles redrew the modern map.",
        ],
        "ar": [
            "في صيف 1914 اشتعلت الحرب العالمية الأولى.",
            "معركة السوم 1916 كانت أشهر المعارك.",
            "دخلت الولايات المتحدة الحرب في 1917.",
            "معاهدة فرساي رسمت خريطة العالم الحديث.",
        ],
    }[lang]
    return {
        "lang": lang,
        "hook": "The First World War" if lang == "en" else "الحرب العالمية الأولى",
        "source_hash": "test",
        "scenes": [
            {"id": i + 1, "narration": bodies[i % len(bodies)], "duration": 8.0, "needs": []}
            for i in range(scenes)
        ],
    }


# --------------------------------------------------------------------------
# the families
# --------------------------------------------------------------------------
def test_three_families_each_with_a_role_recipe_and_motion():
    assert set(FAMILIES) == {"documentary", "explainer", "dense"}
    for family in FAMILIES.values():
        assert family.description
        assert family.words_per_scene > 0
        assert set(family.recipe) == set(SCENE_ROLES)
        for role, types in family.recipe.items():
            assert types, f"{family.name}/{role} has no elements"
        assert family.motion.zoom > 1.0
        assert 0.0 < family.motion.follow <= 1.0


def test_families_are_visibly_different():
    """The three families must not produce the same element mix."""
    mixes = {}
    for name in FAMILIES:
        plan = build_plan(_graph(), {}, fps=24, family=name)
        types = []
        for scene in plan["scenes"]:
            types.extend(e["type"] for e in scene["elements"])
        mixes[name] = types
    assert mixes["documentary"] != mixes["explainer"]
    assert mixes["explainer"] != mixes["dense"]
    # only the documentary family may use a photo
    assert "image" not in mixes["explainer"]


def test_explainer_family_uses_no_images_even_with_assets():
    research = {
        "entities": [
            {
                "name": "Somme",
                "assets": [
                    {"asset": {"path": "assets/x.jpg", "mime": "image/jpeg", "need": "event"}}
                ],
            }
        ]
    }
    graph = _graph()
    graph["scenes"][1]["narration"] = "The Somme in 1916 was months of trench fighting."
    plan = build_plan(graph, research, fps=24, family="explainer")
    assert all(e["type"] != "image" for sc in plan["scenes"] for e in sc["elements"])


def test_unknown_family_is_refused():
    with pytest.raises(ValueError):
        get_family("nope")


def test_scene_roles_follow_the_position():
    assert scene_role(1, 5) == "hook"
    assert scene_role(5, 5) == "close"
    assert scene_role(3, 5) == "explain"
    assert scene_role(2, 5) == "evidence"


# --------------------------------------------------------------------------
# the plan carries the family and the motion rules
# --------------------------------------------------------------------------
def test_plan_carries_the_family_and_its_motion_profile():
    plan = build_plan(_graph(), {}, fps=24, family="documentary")
    family = plan["family"]
    assert family["name"] == "documentary"
    assert family["motion"]["zoom"] > 1.0
    assert "zoom_by_type" in family["motion"]
    assert plan["scenes"][0]["role"] == "hook"
    assert validate_plan(plan)["ok"]


def test_director_uses_the_plan_motion_profile():
    plan = build_plan(_graph(), {}, fps=24, family="explainer")
    director = Director(plan, canvas=(640, 360), out_size=(160, 90), fps=24)
    assert director.motion["zoom"] == plan["family"]["motion"]["zoom"]
    assert director.motion["hold_on_text"] is True


# --------------------------------------------------------------------------
# the draw budget (measured, not guessed)
# --------------------------------------------------------------------------
def test_text_budget_is_reported_per_scene():
    plan = build_plan(_graph(), {}, fps=24, family="explainer")
    for scene in plan["scenes"]:
        budget = scene["text_budget"]
        assert budget["natural_words_per_second"] == NATURAL_DRAWN_WORDS_PER_SECOND
        assert budget["capacity_words"] == int(scene["duration"] * NATURAL_DRAWN_WORDS_PER_SECOND)
        assert budget["drawn_words"] >= 0
        assert isinstance(budget["fits"], bool)


def test_a_scene_that_cannot_be_drawn_is_flagged_with_the_excess():
    graph = _graph()
    # a very long on-screen text in a short scene
    graph["scenes"][2]["narration"] = " ".join(["word"] * 60)
    plan = build_plan(graph, {}, fps=24, family="explainer")
    flagged = [s for s in plan["scenes"] if not s["text_budget"]["fits"]]
    assert flagged, "a 60-word scene in 8 s must be flagged"
    assert flagged[0]["text_budget"]["excess_words"] > 0
    assert plan["stats"]["scenes_over_text_budget"] >= 1


def test_narration_that_is_too_fast_to_read_is_flagged():
    graph = _graph()
    graph["scenes"][2]["narration"] = " ".join(["word"] * 60)
    plan = build_plan(graph, {}, fps=24, family="explainer")
    budget = plan["scenes"][2]["text_budget"]
    assert budget["narration_words_per_second"] > MAX_NARRATION_WORDS_PER_SECOND
    assert budget["fits"] is False


def test_a_fitting_scene_is_not_flagged():
    plan = build_plan(_graph(), {}, fps=24, family="explainer")
    # the evidence/explain scenes carry one short caption and fit their time
    for scene in plan["scenes"][1:]:
        assert scene["text_budget"]["fits"] is True
    # the hook draws a title and a subtitle: it is the dense one, and the
    # report says exactly how many words are too many
    hook = plan["scenes"][0]
    if not hook["text_budget"]["fits"]:
        assert hook["text_budget"]["excess_words"] > 0
        assert hook["text_budget"]["capacity_words"] < hook["text_budget"]["drawn_words"]


# --------------------------------------------------------------------------
# the renderer reports how much it had to rush the drawing
# --------------------------------------------------------------------------
def test_render_reports_the_time_scale_instead_of_hiding_it():
    plan = {
        "fps": {"num": 24, "den": 1},
        "canvas": (640, 360),
        "family": {"motion": {"zoom": 2.0, "follow": 0.07}},
        "scenes": [
            {
                "id": 1,
                "duration": 2.0,
                "start_frame": 0,
                "end_frame": 48,
                "duration_frames": 48,
                "elements": [
                    {
                        "type": "text",
                        "text": "A long sentence that takes far longer to draw than the scene allows",
                        "font": "inter",
                        "size": 64,
                        "rect": [20, 40, 560, 160],
                        "mode": "skeleton",
                        "rtl": False,
                        "color": "#211E1A",
                        "gap": 0.2,
                    }
                ],
            }
        ],
    }
    director = Director(plan, canvas=(640, 360), out_size=(160, 90), fps=24)
    bounds = scene_frame_bounds(plan)
    assert bounds[0]["frames"] == 48
    # the natural drawing is longer than the scene: the fit must compress it
    items, natural, scale = director._prepare_scene(plan["scenes"][0], 2.0)
    assert natural > 2.0
    assert scale > 1.0
    # and the drawing still fits inside the scene (nothing is cut)
    assert max(it["start"] + it["dur"] for it in items) <= 2.0 + 0.01
