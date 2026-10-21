"""Regression: النص على الشاشة يتبع **سعة رسم المشهد** لا رقمًا ثابتًا.

كان التعليق دائمًا أول سبع كلمات مهما كان المشهد قصيرًا: مشهد مدته 4.9ث
لا يسع إلا ~4 كلمات مرسومة (0.95 كلمة/ث)، فكان يُرسم تعليق لا ينتهي في
وقته ويُبلَّغ عنه «خارج ميزانية النص». الآن يُحسب التعليق من سعة المشهد
الحقيقية بعد تطبيق المحاذاة.
"""
from __future__ import annotations

from engine.stages.plan import build_plan


def _scene(duration: float, narration: str) -> dict:
    return {"id": 1, "duration": duration, "narration": narration}


def _drawn_words(scene: dict) -> int:
    return sum(
        len(str(el.get("text") or "").replace("\n", " ").split())
        for el in scene["elements"]
        if el.get("type") == "text"
    )


def test_a_short_scene_gets_a_caption_that_fits_its_time():
    plan = build_plan(
        {
            "lang": "ar",
            "hook": "الذاكرة",
            "scenes": [
                _scene(3.0, "الذاكرة لا تحتفظ بكل شيء لكنها تحتفظ بما نراه")
            ],
        },
        {},
    )
    scene = plan["scenes"][0]
    budget = scene["text_budget"]
    assert budget["capacity_words"] == 2  # 3.0s * 0.95
    assert _drawn_words(scene) <= budget["capacity_words"]
    assert budget["fits"] is True, budget


def test_a_long_scene_keeps_the_natural_caption_length():
    plan = build_plan(
        {
            "lang": "ar",
            "hook": "الذاكرة",
            "scenes": [
                _scene(12.0, "الذاكرة لا تحتفظ بكل شيء لكنها تحتفظ بما نراه")
            ],
        },
        {},
    )
    scene = plan["scenes"][0]
    budget = scene["text_budget"]
    assert budget["capacity_words"] == 11  # 12.0s * 0.95
    assert _drawn_words(scene) <= 7
    assert budget["fits"] is True, budget


def test_every_scene_of_a_plan_fits_its_own_budget():
    plan = build_plan(
        {
            "lang": "ar",
            "hook": "ثلاثة أشياء تقرّر ما يبقى في الذاكرة",
            "scenes": [
                _scene(3.0, "سؤال قصير جدًا يكفي"),
                _scene(9.0, "سطر أطول من Sega تfit هنا لملء المشهد بوضوح"),
                _scene(5.5, "مشهد متوسط الطول يحتاج تعليقًا متوازنًا"),
            ],
        },
        {},
    )
    for scene in plan["scenes"]:
        budget = scene["text_budget"]
        assert budget["fits"] is True, (scene["id"], budget)
        assert _drawn_words(scene) <= budget["capacity_words"]
