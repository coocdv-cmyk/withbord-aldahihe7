from __future__ import annotations

from engine.strokes.text_paths import find_font, text_to_strokes


def test_find_font_prefers_regular_over_italic():
    font = find_font("inter")
    assert "italic" not in font.name.lower()
    assert "oblique" not in font.name.lower()


def test_english_words_advance_left_to_right():
    doc = text_to_strokes("The quick brown fox jumps", find_font("inter"), size=72, mode="outline")
    words = doc.stats["words"]
    assert [w["text"] for w in words] == ["The", "quick", "brown", "fox", "jumps"]
    xs = [w["x0"] for w in words]
    assert xs == sorted(xs)
    assert all(words[i]["x1"] < words[i + 1]["x0"] for i in range(len(words) - 1))
    assert doc.width > 0


def test_arabic_words_remain_right_to_left():
    doc = text_to_strokes("الحرب العالمية الأولى", find_font("arefruqaa"), size=72, rtl=True, mode="outline")
    words = doc.stats["words"]
    assert [w["text"] for w in words] == ["الحرب", "العالمية", "الأولى"]
    xs = [w["x0"] for w in words]
    assert xs == sorted(xs, reverse=True)


def test_mixed_line_keeps_ltr_base_order():
    doc = text_to_strokes("Hello العربية world", find_font("inter"), size=72, mode="outline")
    words = doc.stats["words"]
    assert [w["text"] for w in words] == ["Hello", "العربية", "world"]
    assert words[0]["x0"] < words[2]["x0"]
    assert doc.width > 0
