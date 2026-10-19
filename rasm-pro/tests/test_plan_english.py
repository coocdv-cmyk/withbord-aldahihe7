from __future__ import annotations

from engine.stages.plan import build_plan
from engine.stages.validate_plan import validate_plan


def _graph(lang: str, hook: str, narration: str) -> dict:
    return {
        "lang": lang,
        "hook": hook,
        "source_hash": "test",
        "scenes": [{"id": 1, "narration": narration, "duration": 6.0, "needs": []}],
    }


def test_english_plan_uses_ltr_inter_weights():
    plan = build_plan(_graph("en", "The First World War", "A global conflict reshaped the modern world."), {})
    texts = [e for e in plan["scenes"][0]["elements"] if e["type"] == "text"]
    assert texts
    assert all(e["rtl"] is False for e in texts)
    assert all(e["font"] == "inter" for e in texts)
    assert all(e.get("weight") for e in texts)
    assert validate_plan(plan)["ok"]


def test_arabic_plan_keeps_rtl_and_arabic_fonts():
    plan = build_plan(_graph("ar", "الحرب العالمية الأولى", "صراع عالمي غيّر العالم الحديث."), {})
    texts = [e for e in plan["scenes"][0]["elements"] if e["type"] == "text"]
    assert texts
    assert all(e["rtl"] is True for e in texts)
    assert all(e["font"] in {"arefruqaa", "cairo"} for e in texts)
    assert all("weight" not in e for e in texts)
    assert validate_plan(plan)["ok"]
