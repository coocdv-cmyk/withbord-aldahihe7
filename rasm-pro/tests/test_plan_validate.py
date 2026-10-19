from __future__ import annotations

from pathlib import Path

from engine.stages.validate_plan import validate_plan


def test_valid_plan_with_generated_assets(tmp_path: Path):
    (tmp_path / "bg.png").write_bytes(b"x")
    (tmp_path / "torn.png").write_bytes(b"x")
    plan = {
        "canvas": [1000, 600],
        "fps": 24,
        "lang": "en",
        "scenes": [
            {
                "id": 1,
                "duration": 2.0,
                "elements": [
                    {"type": "background", "rect": [0, 0, 1000, 600], "asset": "bg.png"},
                    {
                        "type": "text",
                        "text": "Hello world",
                        "font": "inter",
                        "size": 72,
                        "rect": [80, 100, 840, 120],
                        "rtl": False,
                        "weight": 600,
                    },
                    {
                        "type": "paper_card",
                        "rect": [120, 260, 720, 260],
                        "texture": "torn.png",
                    },
                ],
            }
        ],
    }
    report = validate_plan(plan, project_dir=tmp_path)
    assert report["ok"], report
    assert report["stats"] == {"scenes": 1, "elements": 3, "duration": 2.0}


def test_invalid_plan_reports_errors_and_warnings(tmp_path: Path):
    plan = {
        "canvas": [1000, 600],
        "fps": 0,
        "lang": "en",
        "scenes": [
            {
                "id": 1,
                "duration": -1,
                "elements": [
                    {"type": "text", "text": "", "font": "missing-font", "size": 0,
                     "rect": [0, 0, 0, 10], "weight": 1000, "rtl": True},
                    {"type": "unknown", "rect": [0, 0, 10, 10]},
                    {"type": "image", "rect": [0, 0, 10, 10], "asset": "nope.png"},
                    {"type": "background", "rect": [0, 0, 10, 10], "asset": "nope.png"},
                ],
            },
            {"id": 1, "duration": 1.0, "elements": []},
        ],
    }
    report = validate_plan(plan, project_dir=tmp_path)
    assert not report["ok"]
    joined = "\n".join(report["errors"])
    for expected in ("fps", "duration", "text is empty", "font", "size", "weight",
                     "unknown type", "asset not found", "duplicate scene id"):
        assert expected in joined
    assert any("background should be the first" in w for w in report["warnings"])
    assert any("English text has rtl=true" in w for w in report["warnings"])


def test_check_assets_can_be_disabled():
    plan = {
        "scenes": [
            {
                "id": "a",
                "duration": 1,
                "elements": [{"type": "svg", "rect": [0, 0, 10, 10], "asset": "missing.svg"}],
            }
        ]
    }
    assert not validate_plan(plan)["ok"]
    assert validate_plan(plan, check_assets=False)["ok"]
