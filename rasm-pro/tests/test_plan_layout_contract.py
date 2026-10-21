"""Regression: the plan must not draw words on top of each other.

The Stage 6 acceptance sample exposed three layout defects that the timing
preflight cannot see (the elements all "fit" their scene, they just cover
each other):

* the hook subtitle repeated the title word for word;
* an evidence scene drew the entity label as a huge headline straight over
  the image, although the torn strip already carries the label;
* the underline of a non-hook scene was drawn through the first line of the
  text instead of below the text block.

These are regressions for the *visible* result, so they are asserted on the
geometry of the plan, not on a rendered file.
"""
from __future__ import annotations

from engine.render.templates import underline
from engine.stages.plan import build_plan


def _graph(narration: str) -> dict:
    return {
        "lang": "ar",
        "hook": narration,
        "source_hash": "test",
        "scenes": [
            {"id": 1, "narration": narration, "duration": 6.0, "needs": []},
            {
                "id": 2,
                "narration": "خريطة الطريق تشرح الطريق هنا",
                "duration": 6.0,
                "needs": [],
            },
            {"id": 3, "narration": "ثم نكتب سطرا آخر هنا", "duration": 6.0, "needs": []},
        ],
    }


def _research() -> dict:
    return {
        "entities": [
            {
                "name": "خريطة",
                "assets": [
                    {"asset": {"path": "assets/generated/map.svg", "mime": "image/svg+xml"}}
                ],
            }
        ]
    }


def _overlaps(a: list[float], b: list[float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def test_the_hook_subtitle_continues_the_sentence_instead_of_repeating_it():
    plan = build_plan(_graph("كم فكرة رائعة نسيناها لأنها بقيت حبيسة ورقة صغيرة"), {})
    texts = [e for e in plan["scenes"][0]["elements"] if e["type"] == "text"]
    assert len(texts) == 2, texts
    title_words = texts[0]["text"].split()
    sub_words = texts[1]["text"].split()
    assert sub_words[: len(title_words)] != title_words, texts
    assert "لأنها" in " ".join(sub_words) or sub_words


def test_an_evidence_label_stays_on_the_strip_and_clears_the_image():
    plan = build_plan(_graph("كم فكرة رائعة نسيناها لأنها بقيت حبيسة ورقة صغيرة"), _research())
    scene = plan["scenes"][1]  # evidence
    strip = next(e for e in scene["elements"] if e["type"] == "torn_strip")
    image = next(e for e in scene["elements"] if e["type"] in ("image", "svg"))
    texts = [e for e in scene["elements"] if e["type"] == "text"]
    assert texts, scene["elements"]

    label = texts[0]
    sx, sy, sw, sh = strip["rect"]
    lx, ly, lw, lh = label["rect"]
    # the label belongs on the torn strip
    assert sx <= lx and lx + lw <= sx + sw
    assert sy <= ly and ly + lh <= sy + sh
    # and it is a label, not a headline
    assert label["size"] <= 120, label
    # nothing is drawn on top of the image
    for element in texts:
        assert not _overlaps(element["rect"], image["rect"]), element


def test_the_underline_is_drawn_below_the_text_and_not_through_it():
    plan = build_plan(_graph("كم فكرة رائعة نسيناها لأنها بقيت حبيسة ورقة صغيرة"), {})
    scene = plan["scenes"][2]  # explain
    text = next(e for e in scene["elements"] if e["type"] == "text")
    line = next(e for e in scene["elements"] if e["type"] == "underline")
    strokes = underline(
        line["rect"],
        double=bool(line.get("double")),
        brush=float(line.get("brush", 4.5)),
        offset=float(line.get("offset", 10.0)),
    )
    ys = [point[1] for stroke in strokes for point in stroke.points]
    assert ys, line
    text_bottom = text["rect"][1] + text["rect"][3]
    assert min(ys) > text_bottom, (min(ys), text_bottom)
