"""Credits follow the plan and the human decision — nothing else.

Two failure modes matter:

* an asset that is **used** but not approved must not be credited, and
* an asset that is approved but **not used** in this video must not be
  credited either (the credits travel with the episode, not the library).
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.core.assets import append_decision
from engine.research.store import AssetStore


def _write_project(tmp_path: Path) -> tuple[Path, dict]:
    pd = tmp_path / "project"
    for d in ("assets", "research", "storyboard"):
        (pd / d).mkdir(parents=True, exist_ok=True)
    for name in ("used-approved", "unused-approved", "used-deferred", "used-rejected"):
        (pd / "assets" / f"{name}.png").write_bytes(b"not-a-real-png")

    assets = [
        {
            "asset_id": f"a-00000000000{i}",
            "path": f"assets/{name}.png",
            "sha256": f"{i}" * 64,
            "license": {"name": "CC0"},
            "origin": {"kind": "download"},
        }
        for i, name in enumerate(
            ("used-approved", "unused-approved", "used-deferred", "used-rejected"), 1
        )
    ]
    registry = [
        {
            "path": f"assets/{name}.png",
            "sha256": f"{i}" * 64,
            "title": name.replace("-", " ").title(),
            "author": "Tester",
            "license": "CC0",
            "page_url": f"https://example.invalid/{name}",
        }
        for i, name in enumerate(
            ("used-approved", "unused-approved", "used-deferred", "used-rejected"), 1
        )
    ]
    plan = {
        "scenes": [
            {
                "id": 1,
                "elements": [
                    {"type": "image", "asset": "assets/used-approved.png", "rect": [0, 0, 10, 10]},
                    {"type": "image", "asset": "assets/used-deferred.png", "rect": [0, 0, 10, 10]},
                    {"type": "image", "asset": "assets/used-rejected.png", "rect": [0, 0, 10, 10]},
                ],
            }
        ]
    }
    (pd / "storyboard" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (pd / "project.json").write_text(
        json.dumps({"id": "credits-test", "assets": assets}), encoding="utf-8"
    )
    (pd / "research" / "assets.json").write_text(
        json.dumps(registry, ensure_ascii=False), encoding="utf-8"
    )
    append_decision(pd, asset_id="a-000000000001", path="assets/used-approved.png", decision="approved", reviewer="tester")
    append_decision(pd, asset_id="a-000000000002", path="assets/unused-approved.png", decision="approved", reviewer="tester")
    append_decision(pd, asset_id="a-000000000003", path="assets/used-deferred.png", decision="deferred", reviewer="tester")
    append_decision(pd, asset_id="a-000000000004", path="assets/used-rejected.png", decision="rejected", reviewer="tester")
    return pd, plan


def test_credits_are_exactly_used_and_approved(tmp_path: Path):
    pd, plan = _write_project(tmp_path)
    store = AssetStore(pd)
    text = store.credits_markdown(plan=plan)

    credited = [line for line in text.splitlines() if line.startswith("- **")]
    assert len(credited) == 1
    assert "Used Approved" in credited[0]
    assert "Unused Approved" not in text
    assert "Used Rejected" not in text
    # Deferred-but-used is disclosed separately, never presented as a credit.
    deferred = text.split("## أصول مستخدمة قيد الاعتماد", 1)
    assert len(deferred) == 2
    assert "Used Deferred" in deferred[1]
    assert "Used Approved" not in deferred[1]


def test_write_credits_uses_the_plan_and_is_reproducible(tmp_path: Path):
    pd, plan = _write_project(tmp_path)
    store = AssetStore(pd)
    path = store.write_credits(plan=plan)
    first = path.read_text(encoding="utf-8")
    second = AssetStore(pd).write_credits(plan=plan).read_text(encoding="utf-8")
    assert first == second
    assert "Used Approved" in first and "Used Rejected" not in first
