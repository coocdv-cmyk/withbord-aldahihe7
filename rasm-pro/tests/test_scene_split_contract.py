"""Regression: المشاهد يجب أن **لا تعبر فقرة الكاتب أبدًا**.

The first engine-driven episode exposed it: the heuristic splitter merged
sentences across the author's blank lines and cut a sentence in half, so the
narration of scene 4 started in the middle of a thought and the plan drew a
meaningless fragment.  The paragraph is the writer's intent — it is a hard
boundary.

Three rules are pinned here:
1. a scene never contains text from two paragraphs;
2. a short question at the start of a paragraph does not become its own scene;
3. a too-short tail is merged into the previous scene instead of standing
   alone (a three-word scene cannot be drawn and cannot be narrated).
"""
from __future__ import annotations

from engine.stages.understanding import (
    MIN_MERGE_WORDS,
    SCENE_WORDS_TARGET,
    heuristic_scenes,
)


def test_a_scene_never_crosses_a_paragraph_boundary():
    text = (
        "الجملة الأولى من الفقرة الأولى وهي أطول من الحد المستهدف بكلمات كثيرة "
        "كي يصل العدد الكافي من الكلمات هنا. "
        "ثم جملة ثانية في الفقرة الأولى.\n\n"
        "وأول جملة في الفقرة الثانية وهي أيضًا طويلة بما يكفي لأن تكون مشهدًا "
        "مستقلًا بكلماتها الكثيرة. "
        "وثانية جملة في الفقرة الثانية."
    )
    scenes = heuristic_scenes(text)
    assert scenes
    for scene in scenes:
        # a scene that contains the end of paragraph one must not also
        # contain the beginning of paragraph two
        assert not ("الفقرة الأولى" in scene["narration"] and "الفقرة الثانية" in scene["narration"])


def test_a_short_question_does_not_become_its_own_scene():
    text = (
        "لماذا ننسى؟ "
        "ثلاثة أشياء تقرّر ما يبقى في الذاكرة وأحدها ليس الذكاء بل النوم. "
        "في هذا المشهد نكشف القاعدة ثم ننتقل إلى خطوة عملية تنفعك اليوم."
    )
    scenes = heuristic_scenes(text)
    assert scenes[0]["narration"].startswith("لماذا ننسى؟")
    assert scenes[0]["words"] >= 8, scenes[0]


def test_a_short_tail_is_merged_into_the_previous_scene():
    text = (
        "جملة طويلة بما يكفي لتشكيل مشهد كامل Words words words words words words words words. "
        "قصير."
    )
    scenes = heuristic_scenes(text)
    assert len(scenes) == 1, scenes
    assert "قصير" in scenes[0]["narration"]


def test_the_scene_target_is_big_enough_for_the_drawing_budget():
    # 0.95 drawn words per second, and a caption of 7 words needs ~7.4s;
    # a scene of SCENE_WORDS_TARGET words is spoken at ~2.45 words/second.
    seconds = SCENE_WORDS_TARGET / 2.45
    assert seconds * 0.95 >= 7.0, (SCENE_WORDS_TARGET, seconds)
    assert MIN_MERGE_WORDS >= 10
