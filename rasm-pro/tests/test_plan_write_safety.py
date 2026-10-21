"""Regression: a rebuild must never overwrite an existing plan (Stage 6 audit)."""
from __future__ import annotations

import json
from pathlib import Path

from engine.stages.plan import build_plan, save_plan


def _graph() -> dict:
    return {
        "lang": "en",
        "hook": "A hook",
        "source_hash": "t",
        "scenes": [{"id": 1, "narration": "One sentence here.", "duration": 6.0, "needs": []}],
    }


def test_saving_a_plan_never_overwrites_an_existing_file(tmp_path: Path):
    pd = tmp_path / "p"
    (pd / "storyboard").mkdir(parents=True)
    legacy = pd / "storyboard" / "plan.json"
    legacy.write_text('{"legacy": true}\n', encoding="utf-8")
    before = legacy.read_bytes()

    plan = build_plan(_graph(), {}, fps=24)
    first = save_plan(plan, pd)
    assert first != legacy
    assert legacy.read_bytes() == before, "the existing plan must not be touched"

    second = save_plan(plan, pd)
    assert second != first
    assert first.exists()


def test_names_never_collide_with_the_legacy_sequence(tmp_path: Path):
    pd = tmp_path / "p"
    (pd / "storyboard").mkdir(parents=True)
    for name in ("plan.json", "plan_v2.json"):
        (pd / "storyboard" / name).write_text('{"x": 1}\n', encoding="utf-8")
    plan = build_plan(_graph(), {}, fps=24)
    out = save_plan(plan, pd)
    assert out.name == "plan_v3.json"
    assert json.loads(out.read_text(encoding="utf-8"))["scenes"]


def test_a_free_name_is_used_when_nothing_exists(tmp_path: Path):
    pd = tmp_path / "p"
    plan = build_plan(_graph(), {}, fps=24)
    out = save_plan(plan, pd)
    assert out.name == "plan.json"
