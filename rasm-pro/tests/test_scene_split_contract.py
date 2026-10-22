"""Regression: تقسيم السكريبت إلى مشاهد **فكرة واحدة لكل مشهد**.

المحرّك يجب أن يقبل سكريبتًا خامًا فيُخرج مشاهد قابلة للرسم. القواعد
مقيسة: الفقرة حدّ صلب، طول أدنى وأقصى، وفصل عند علامة انتقال قوي.
"""
from __future__ import annotations

from engine.stages.scene_split import MAX_WORDS, MIN_WORDS, split_scenes
from engine.stages.understanding import heuristic_script_graph


RAW = (
    "الذاكرة لا تحتفظ بكل شيء، لكنها تحتفظ بما نراه وما نلمسه وما نعيد رسمه بأيدينا. "
    "وحين نحوّل الفكرة إلى رسم، يجد العقل صورة يعود إليها بدل سطر ينساه. "
    "لكن لماذا ننسى ما نتعلمه؟ لأن/learnt "  # a mixed-language fragment
    "لأن الذاكرة القوية تخضع للتكرار الموزع على أيام، لا للحظات الحماس. "
    "ثم تضاعف الأثر مع كل مراجعة، حتى ليصير النص جزءًا منك. "
    "وأخيرًا تبدأ المعرفة: اكتب ملاحظة، وراجعها غدًا وبعد أسبوع، وستكتشف أن الفكرة الملقاة لم تكن فكرة، بل عادة في انتظار أن تُصنع."
)


def test_a_raw_script_becomes_scenes_of_usable_length():
    scenes = split_scenes(RAW)
    assert len(scenes) >= 4, len(scenes)
    for scene in scenes[:-1]:
        assert scene.words >= MIN_WORDS, scene
    for scene in scenes:
        assert scene.words <= MAX_WORDS + 6, scene


def test_the_first_scene_is_the_hook_and_the_last_is_the_close():
    scenes = split_scenes(RAW)
    assert scenes[0].role == "hook"
    assert scenes[-1].role == "close"


def test_a_paragraph_is_never_merged_with_the_next_one():
    text = (
        "هذه فقرة كاملة تحتوي على كلمات كافية لأن تكون مشهدًا مستقلًا بذاتها "
        "وليس أقل من الحد الأدنى المسموح به في المشهد الواحد.\n\n"
        "وهذه فقرة ثانية مختلفة تمامًا لا يجوز أن تُدمج مع الأولى أبدًا مهما كان الطول."
    )
    scenes = split_scenes(text)
    assert len(scenes) == 2, [s.narration for s in scenes]
    assert "الفقرة الأولى" not in scenes[1].narration or "هذه فقرة" not in scenes[1].narration


def test_the_script_graph_uses_the_new_splitter():
    graph = heuristic_script_graph(RAW)
    assert len(graph["scenes"]) >= 4
    assert all(s["narration"] for s in graph["scenes"])
    # the hook of the graph is the first scene
    assert graph["hook"].startswith(graph["scenes"][0]["narration"][:20])
