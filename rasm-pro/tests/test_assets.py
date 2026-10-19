from __future__ import annotations

from PIL import Image

from engine.assets import brain, procedural
from engine.assets.qa import analyze
from engine.assets.style import load_style


def test_style_pack_has_required_kinds():
    style = load_style("paper_ink_v1")
    assert style["id"] == "paper_ink_v1"
    for kind in ("aged_paper", "parchment", "torn_paper", "tape_strip", "poster", "vintage_poster"):
        assert kind in style["kinds"]


def test_procedural_is_deterministic():
    style = load_style("paper_ink_v1")
    a = procedural.generate("aged_paper", 640, 480, 123, style)
    b = procedural.generate("aged_paper", 640, 480, 123, style)
    c = procedural.generate("aged_paper", 640, 480, 124, style)
    assert a.size == (640, 480)
    assert a.tobytes() == b.tobytes()
    assert a.tobytes() != c.tobytes()


def test_qa_accepts_clean_paper():
    style = load_style("paper_ink_v1")
    paper = Image.new("RGB", (1024, 768), (239, 227, 207))
    result = analyze(paper, style, style["kinds"]["aged_paper"], purpose="background")
    assert result["faces"] == 0
    assert result["palette_distance"] < 20
    assert result["score"] > 50


def test_qa_rejects_neon():
    style = load_style("paper_ink_v1")
    neon = Image.new("RGB", (1024, 768), (0, 255, 0))
    result = analyze(neon, style, style["kinds"]["aged_paper"], purpose="background")
    assert result["pass"] is False
    assert any("saturation" in f or "palette" in f for f in result["failures"])


def test_brain_history_chooses_paper():
    result = brain.suggest("مشهد عن الحرب العالمية الأولى وأرشيف قديم", "background")
    assert result["mood"] == "history"
    assert result["kind"] in {"aged_paper", "newsprint", "parchment", "map_fragment", "vintage_poster"}
    assert result["alternatives"]
