"""Stage 3 contract: asset identity, human approval and the production gate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.core.assets import (
    ApprovalError,
    append_decision,
    asset_id_for,
    evaluate_gate,
    link_plan_assets,
    load_decisions,
    plan_asset_refs,
    sync_manifest_approvals,
)
from engine.core.project import read_manifest, write_manifest
from engine.core.util import sha256_file


def _make_project(tmp_path: Path, *, license_name: str = "CC0", origin: bool = True) -> tuple[Path, dict, dict]:
    """A project with one asset and a plan that uses it."""
    pd = tmp_path / "p3"
    (pd / "assets").mkdir(parents=True)
    (pd / "storyboard").mkdir()
    (pd / "research").mkdir()
    asset = pd / "assets" / "a.jpg"
    asset.write_bytes(b"fake-image-bytes")
    digest = sha256_file(asset)

    manifest = {
        "schema_version": "1.0",
        "project_id": "p3",
        "title": "P3",
        "language": "ar",
        "canvas": [2560, 1440],
        "fps": {"num": 24, "den": 1},
        "status": "planned",
        "created_at": "2026-10-20T00:00:00Z",
        "updated_at": "2026-10-20T00:00:00Z",
        "paths": {},
        "storyboard": {"active": "storyboard/plan.json", "sha256": "", "format_version": "1.0"},
        "audio": {},
        "asset_policy": {
            "generated_is_evidence": False,
            "retrieved_requires_approval": True,
            "requires_origin": True,
            "requires_license": True,
            "final_render_requires_approval": True,
        },
        "assets": [
            {
                "path": "assets/a.jpg",
                "asset_id": asset_id_for(digest, "assets/a.jpg"),
                "sha256": digest,
                "bytes": asset.stat().st_size,
                "kind": "photo",
                "mime": "image/jpeg",
                "origin": {"kind": "Wikimedia Commons", "url": "https://example.invalid/a.jpg"} if origin else {},
                "license": {"name": license_name, "url": "", "attribution_required": False},
                "approved_by": None,
                "approved_at": None,
                "status": "retrieved",
            }
        ],
        "unresolved": [],
        "renders": [],
        "render": {"fps_source": "plan"},
        "studio": {"kind": "rasm-pro", "project_id": "p3"},
    }
    write_manifest(pd, manifest)

    plan = {
        "fps": {"num": 24, "den": 1},
        "canvas": [2560, 1440],
        "scenes": [
            {
                "id": 1,
                "duration": 2.0,
                "narration": "scene one",
                "needs": [],
                "assets_used": [str(asset)],
                "elements": [{"type": "image", "asset": str(asset), "rect": [0, 0, 800, 600]}],
            }
        ],
    }
    (pd / "storyboard" / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return pd, manifest, plan


def _approve(pd: Path, manifest: dict, decision: str = "approved", reviewer: str = "tester") -> dict:
    asset = manifest["assets"][0]
    append_decision(
        pd,
        asset_id=asset["asset_id"],
        path=asset["path"],
        decision=decision,
        reviewer=reviewer,
        note="",
        license=asset["license"]["name"],
    )
    updated = sync_manifest_approvals(manifest, pd)
    write_manifest(pd, updated)
    return updated


def test_asset_id_is_content_derived_and_stable():
    a = asset_id_for("33ff2ae0e7b2b0a8d4cf81c2b5e28144b056e328cff53cb8a37d954842e4393f", "assets/x.jpg")
    b = asset_id_for("33FF2AE0E7B2B0A8D4CF81C2B5E28144B056E328CFF53CB8A37D954842E4393F", "assets/x.jpg")
    assert a == b == "a-33ff2ae0e7b2"
    # the same bytes under a different path keep the same id
    assert asset_id_for("33ff2ae0e7b2b0a8d4cf81c2b5e28144b056e328cff53cb8a37d954842e4393f", "other.jpg") == a


def test_decision_log_is_append_only(tmp_path):
    pd, manifest, _ = _make_project(tmp_path)
    asset = manifest["assets"][0]
    append_decision(pd, asset_id=asset["asset_id"], path=asset["path"], decision="deferred", reviewer="a")
    append_decision(pd, asset_id=asset["asset_id"], path=asset["path"], decision="approved", reviewer="b")
    records = load_decisions(pd)
    assert [r["decision"] for r in records] == ["deferred", "approved"]
    assert records[0]["reviewer"] == "a"
    # the log itself is never rewritten
    assert (pd / "research" / "approvals.jsonl").read_text(encoding="utf-8").count("\n") == 2


def test_decision_requires_reviewer_and_known_value(tmp_path):
    pd, manifest, _ = _make_project(tmp_path)
    asset = manifest["assets"][0]
    with pytest.raises(ApprovalError):
        append_decision(pd, asset_id=asset["asset_id"], path=asset["path"], decision="approved", reviewer="")
    with pytest.raises(ApprovalError):
        append_decision(pd, asset_id=asset["asset_id"], path=asset["path"], decision="maybe", reviewer="a")


def test_manifest_projection_reflects_the_latest_decision(tmp_path):
    pd, manifest, _ = _make_project(tmp_path)
    updated = _approve(pd, manifest)
    entry = updated["assets"][0]
    assert entry["approval"]["decision"] == "approved"
    assert entry["approval"]["reviewer"] == "tester"
    assert entry["approved_by"] == "tester"
    assert entry["approved_at"]
    assert updated["approval_log"]["records"] == 1
    assert updated["approval_log"]["path"] == "research/approvals.jsonl"
    # the manifest on disk carries the same state
    on_disk = read_manifest(pd, required=True)
    assert on_disk["assets"][0]["approval"]["decision"] == "approved"


def test_final_gate_blocks_unapproved_assets(tmp_path):
    pd, manifest, plan = _make_project(tmp_path)
    report = evaluate_gate(plan, pd, manifest=manifest, mode="final")
    assert not report.ok
    assert [b["reason"] for b in report.blocking] == ["asset-not-approved"]
    assert report.blocking[0]["asset_id"] == manifest["assets"][0]["asset_id"]


def test_preview_gate_allows_but_warns(tmp_path):
    pd, manifest, plan = _make_project(tmp_path)
    report = evaluate_gate(plan, pd, manifest=manifest, mode="preview")
    assert report.ok
    assert [w["reason"] for w in report.warnings] == ["asset-not-approved"]


def test_rejected_asset_blocks_in_every_mode(tmp_path):
    pd, manifest, plan = _make_project(tmp_path)
    _approve(pd, manifest, decision="rejected", reviewer="tester")
    for mode in ("final", "preview"):
        report = evaluate_gate(plan, pd, manifest=manifest, mode=mode)
        assert not report.ok
        assert [b["reason"] for b in report.blocking] == ["asset-rejected"]


def test_approved_asset_without_license_blocks_final(tmp_path):
    pd, manifest, plan = _make_project(tmp_path, license_name="UNKNOWN")
    _approve(pd, manifest)
    report = evaluate_gate(plan, pd, manifest=manifest, mode="final")
    assert not report.ok
    assert "asset-license-missing" in [b["reason"] for b in report.blocking]
    preview = evaluate_gate(plan, pd, manifest=manifest, mode="preview")
    assert preview.ok
    assert "asset-license-missing" in [w["reason"] for w in preview.warnings]


def test_approved_asset_without_origin_blocks_final(tmp_path):
    pd, manifest, plan = _make_project(tmp_path, origin=False)
    _approve(pd, manifest)
    report = evaluate_gate(plan, pd, manifest=manifest, mode="final")
    assert not report.ok
    assert "asset-origin-missing" in [b["reason"] for b in report.blocking]


def test_generated_asset_may_not_be_used_as_evidence(tmp_path):
    pd, manifest, plan = _make_project(tmp_path)
    manifest["assets"][0]["origin"]["kind"] = "generated"
    plan["scenes"][0]["evidence"] = True
    _approve(pd, manifest)
    report = evaluate_gate(plan, pd, manifest=manifest, mode="preview")
    assert not report.ok
    assert "generated-as-evidence" in [b["reason"] for b in report.blocking]


def test_assets_not_used_in_the_plan_do_not_block(tmp_path):
    pd, manifest, plan = _make_project(tmp_path)
    extra = pd / "assets" / "b.jpg"
    extra.write_bytes(b"other")
    manifest["assets"].append(
        {
            "path": "assets/b.jpg",
            "asset_id": asset_id_for(sha256_file(extra), "assets/b.jpg"),
            "sha256": sha256_file(extra),
            "bytes": extra.stat().st_size,
            "origin": {"kind": "Wikimedia Commons", "url": "https://example.invalid/b.jpg"},
            "license": {"name": "CC0", "url": "", "attribution_required": False},
        }
    )
    report = evaluate_gate(plan, pd, manifest=manifest, mode="final")
    assert not report.ok
    assert len(report.blocking) == 1
    assert report.blocking[0]["path"] == "assets/a.jpg"


def test_plan_refs_resolve_absolute_paths_to_relative(tmp_path):
    pd, manifest, plan = _make_project(tmp_path)
    refs = plan_asset_refs(plan, pd, manifest=manifest)
    assert len(refs) == 1
    assert refs[0].path == "assets/a.jpg"
    assert refs[0].asset_id == manifest["assets"][0]["asset_id"]
    assert refs[0].exists is True
    assert refs[0].scenes == ["1"]


def test_link_plan_assets_rewrites_to_relative_and_adds_ids(tmp_path):
    pd, manifest, plan = _make_project(tmp_path)
    linked, changes = link_plan_assets(plan, pd, manifest=manifest)
    scene = linked["scenes"][0]
    assert scene["assets_used"] == ["assets/a.jpg"]
    assert scene["elements"][0]["asset"] == "assets/a.jpg"
    assert scene["elements"][0]["asset_id"] == manifest["assets"][0]["asset_id"]
    assert scene["asset_ids"] == [manifest["assets"][0]["asset_id"]]
    assert len(changes) == 2
    # the original plan object is untouched
    assert str(plan["scenes"][0]["assets_used"][0]).endswith("a.jpg")
    assert Path(plan["scenes"][0]["assets_used"][0]).is_absolute()


def test_link_plan_assets_is_idempotent(tmp_path):
    pd, manifest, plan = _make_project(tmp_path)
    linked, changes = link_plan_assets(plan, pd, manifest=manifest)
    again, changes2 = link_plan_assets(linked, pd, manifest=manifest)
    assert changes2 == []
    assert again["scenes"][0]["assets_used"] == linked["scenes"][0]["assets_used"]


def test_unknown_gate_mode_is_rejected(tmp_path):
    pd, manifest, plan = _make_project(tmp_path)
    with pytest.raises(ApprovalError):
        evaluate_gate(plan, pd, manifest=manifest, mode="ship-it")


def test_broken_decision_log_is_reported(tmp_path):
    pd, manifest, _ = _make_project(tmp_path)
    log = pd / "research" / "approvals.jsonl"
    log.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ApprovalError):
        load_decisions(pd)
