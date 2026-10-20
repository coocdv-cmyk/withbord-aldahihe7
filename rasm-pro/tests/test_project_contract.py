from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.core.project import (
    MANIFEST_NAME,
    ProjectError,
    activate_plan,
    infer_manifest,
    load_active_plan,
    read_manifest,
    resolve_project_path,
    utc_now,
    validate_manifest,
    write_manifest,
)
from engine.core.util import sha256_file

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "engine" / "core" / "schema"


def _make_project(tmp_path: Path) -> Path:
    pd = tmp_path / "p1"
    (pd / "script").mkdir(parents=True)
    (pd / "research").mkdir()
    (pd / "storyboard").mkdir()
    (pd / "assets").mkdir()
    asset = pd / "assets" / "a.txt"
    asset.write_text("asset-data", encoding="utf-8")
    digest = sha256_file(asset)
    (pd / "script" / "scriptgraph.json").write_text(
        json.dumps({"lang": "en", "scenes": [{"id": 1, "narration": "hello"}]}),
        encoding="utf-8",
    )
    (pd / "script" / "script.txt").write_text("hello", encoding="utf-8")
    (pd / "research" / "research.json").write_text(
        json.dumps({"entities": []}), encoding="utf-8"
    )
    (pd / "research" / "assets.json").write_text(
        json.dumps(
            [
                {
                    "path": "assets/a.txt",
                    "sha256": digest,
                    "bytes": asset.stat().st_size,
                    "kind": "document",
                    "mime": "text/plain",
                    "source": "local",
                    "url": "https://example.invalid/a",
                    "page_url": "https://example.invalid/a",
                    "retrieved_at": "2026-10-20T00:00:00Z",
                    "title": "A",
                    "author": "Tester",
                    "license": "CC0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "attr": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    plan_v2 = {
        "fps": {"num": 24, "den": 1},
        "canvas": [640, 360],
        "scenes": [
            {
                "id": 1,
                "duration": 1.0,
                "start_frame": 0,
                "end_frame": 24,
                "duration_frames": 24,
                "elements": [],
                "narration": "hello",
            }
        ],
        "stats": {"scenes": 1, "elements": 0, "duration": 1.0},
    }
    (pd / "storyboard" / "plan_v2.json").write_text(
        json.dumps(plan_v2, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    legacy = {"fps": 30, "canvas": [640, 360], "scenes": [{"id": 1, "duration": 1.0, "elements": []}]}
    (pd / "storyboard" / "plan.json").write_text(json.dumps(legacy), encoding="utf-8")
    return pd


def test_manifest_roundtrip_and_migration_keeps_legacy_plan(tmp_path):
    pd = _make_project(tmp_path)
    man = infer_manifest(
        pd,
        project_id="p1",
        title="Test",
        language="en",
        now="2026-10-20T00:00:00Z",
    )
    assert man["storyboard"]["active"] == "storyboard/plan_v2.json"
    assert man["fps"] == {"num": 24, "den": 1}
    assert man["assets"][0]["origin"]["kind"] == "local"
    assert man["assets"][0]["approved_by"] is None
    report = validate_manifest(man, pd)
    assert report["ok"], report["errors"]
    write_manifest(pd, man)
    assert read_manifest(pd) == man
    assert (pd / "storyboard" / "plan.json").exists()
    plan, plan_path = load_active_plan(pd)
    assert plan_path.name == "plan_v2.json"
    assert plan["fps"] == {"num": 24, "den": 1}


def test_tampered_plan_hash_is_rejected(tmp_path):
    pd = _make_project(tmp_path)
    man = infer_manifest(pd, project_id="p1", title="Test", now="2026-10-20T00:00:00Z")
    write_manifest(pd, man)
    plan_path = pd / "storyboard" / "plan_v2.json"
    plan_path.write_text(plan_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ProjectError):
        load_active_plan(pd)
    report = validate_manifest(read_manifest(pd), pd)
    assert not report["ok"]
    assert any("sha256" in e for e in report["errors"])


def test_manifest_paths_cannot_escape_project(tmp_path):
    pd = _make_project(tmp_path)
    with pytest.raises(ProjectError):
        resolve_project_path(pd, "../outside.json")
    with pytest.raises(ProjectError):
        resolve_project_path(pd, str((tmp_path / "absolute.json").resolve()))
    man = infer_manifest(pd, project_id="p1", title="Test", now="2026-10-20T00:00:00Z")
    man["storyboard"]["active"] = "../outside.json"
    report = validate_manifest(man, pd)
    assert not report["ok"]


def test_activate_plan_updates_hash_and_rate(tmp_path):
    pd = _make_project(tmp_path)
    man = infer_manifest(pd, project_id="p1", title="Test", now="2026-10-20T00:00:00Z")
    write_manifest(pd, man)
    activate_plan(pd, "storyboard/plan.json")
    loaded = read_manifest(pd)
    assert loaded["storyboard"]["active"] == "storyboard/plan.json"
    assert loaded["fps"] == {"num": 30, "den": 1}
    assert loaded["storyboard"]["sha256"] == sha256_file(pd / "storyboard" / "plan.json")
    plan, _ = load_active_plan(pd)
    assert plan["fps"] == 30


def test_activate_plan_accepts_absolute_inside_project_only(tmp_path):
    pd = _make_project(tmp_path)
    man = infer_manifest(pd, project_id="p1", title="Test", now="2026-10-20T00:00:00Z")
    write_manifest(pd, man)
    activate_plan(pd, pd / "storyboard" / "plan.json")
    loaded = read_manifest(pd)
    assert loaded["storyboard"]["active"] == "storyboard/plan.json"
    with pytest.raises(ProjectError):
        activate_plan(pd, tmp_path / "outside.json")


def test_manifest_is_idempotent_when_inputs_unchanged(tmp_path):
    pd = _make_project(tmp_path)
    now = "2026-10-20T00:00:00Z"
    first = infer_manifest(pd, project_id="p1", title="Test", now=now)
    write_manifest(pd, first)
    second = infer_manifest(pd, project_id="p1", title="Test", now=now)
    assert first == second
    assert json.loads((pd / MANIFEST_NAME).read_text(encoding="utf-8")) == second


def test_schemas_are_valid_json_and_have_expected_roots():
    for name in ("project.schema.json", "plan.schema.json"):
        data = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        assert data["$schema"].startswith("https://json-schema.org/")
        assert data["type"] == "object"
        assert "properties" in data
