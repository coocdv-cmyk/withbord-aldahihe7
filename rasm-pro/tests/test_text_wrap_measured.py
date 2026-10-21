"""Regression: النص على الشاشة **لا يتجاوز صندوقه** (يُقاس، لا يُخمَّن).

كان التغليف بعدد كلمات ثابت: «dug up in 1972» (عرضها الحقيقي 916px عند
حجم 150) في عمود بعرض 920px — فتُقصّ الكلمة الأخيرة على الشاشة. والحلقة
الأولى بالإنجليزية أظهرت ذلك في ثلاثة مشاهد.

الآن: التغليف يقيس عرض كل سطر بالخط الحقيقي (PIL) فلا يخرج سطر عن صندوقه.
"""
from __future__ import annotations

from engine.stages.plan import _wrap_to_width, build_plan


def test_a_line_never_exceeds_the_measured_width():
    text = "dug up in 1972"
    body = _wrap_to_width(text, font_name="cairo", size=150, width=920)
    lines = body.split("\n")
    assert len(lines) >= 1
    from engine.strokes import text_to_strokes, find_font

    doc = text_to_strokes(body, find_font("cairo"), 150, mode="skeleton", rtl=False)
    xs = [p[0] for st in doc.strokes for p in st.points]
    width = max(xs) - min(xs)
    assert width <= 920 * 1.02, width


def test_a_wide_column_keeps_more_words_on_one_line():
    narrow = _wrap_to_width(
        "Thirteen chapters, each one line", font_name="cairo", size=190, width=920
    )
    wide = _wrap_to_width(
        "Thirteen chapters, each one line", font_name="cairo", size=190, width=2300
    )
    assert len(narrow.split("\n")) >= len(wide.split("\n"))


def test_the_plan_wraps_by_measurement_not_by_word_count():
    plan = build_plan(
        {
            "lang": "en",
            "hook": "The Art of War",
            "scenes": [
                {"id": 1, "duration": 8.0, "narration": "The Art of War"},
                {"id": 2, "duration": 14.0, "narration": "The Art of War, dug up in 1972"},
                {"id": 3, "duration": 14.0, "narration": "The Art of War, dug up in 1972"},
            ],
        },
        {},
    )
    evidence = plan["scenes"][1]
    texts = [e for e in evidence["elements"] if e.get("type") == "text"]
    assert texts
    from engine.strokes import text_to_strokes, find_font

    for element in texts:
        doc = text_to_strokes(
            element["text"], find_font(element["font"]), element["size"], mode="skeleton", rtl=False
        )
        if not doc.strokes:
            continue
        xs = [p[0] for st in doc.strokes for p in st.points]
        width = max(xs) - min(xs)
        assert width <= element["rect"][2] * 1.05, (element["text"], width, element["rect"])
