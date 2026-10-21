"""Regression: **أصل مرفوض لا يدخل الخطة أصلًا**.

البحث يجد الأصول بالاسم، وقد يُرجع صورة لا تمثّل الكيان: صورة قطار
لكيان «أوكرانيا»، أو سفن حديثة لكيان «تسي تشي كوانغ».  القرار البشري
(رفض) كان يصل إلى بوابة الرندر فقط — أمّا الخطة فكانت ما زالت تختار
الأصل المرفوض وترسمه.

الآن: الرفض يخرج الأصل من فهرس الخطة، فالخطة تختار الأصل التالي، والرندر
لا يرى أصلًا مرفوضًا أصلًا.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.core.assets import append_decision
from engine.stages.plan import build_plan


def _research(assets: list[str]) -> dict:
    return {
        "entities": [
            {
                "name": "Ukraine",
                "type": "country",
                "assets": [
                    {"asset": {"path": p, "mime": "image/jpeg", "title": p, "license": "CC0"}}
                    for p in assets
                ],
            }
        ]
    }


def test_a_rejected_asset_is_not_offered_to_the_plan(tmp_path: Path):
    project = tmp_path / "demo"
    (project / "assets").mkdir(parents=True)
    (project / "research").mkdir(parents=True)
    (project / "assets" / "train.jpg").write_bytes(b"x" * 100)
    (project / "assets" / "map.jpg").write_bytes(b"y" * 100)

    append_decision(
        project,
        asset_id="a-000000000001",
        path="assets/train.jpg",
        decision="rejected",
        reviewer="tester",
        note="a train does not depict a country",
    )
    plan = build_plan(
        {
            "lang": "en",
            "hook": "Ukraine",
            "scenes": [
                {"id": 1, "duration": 8.0, "narration": "Ukraine, 2022: defend everywhere"},
                {"id": 2, "duration": 8.0, "narration": "Ukraine, 2022: defend everywhere"},
                {"id": 3, "duration": 8.0, "narration": "Ukraine, 2022: defend everywhere"},
            ],
        },
        _research(["assets/train.jpg", "assets/map.jpg"]),
        project_dir=project,
    )
    used = plan["scenes"][1]["assets_used"]
    assert used == ["assets/map.jpg"], used
