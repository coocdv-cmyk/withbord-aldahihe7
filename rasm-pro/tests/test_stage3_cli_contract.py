"""Stage 3 CLI contract: the approval workflow and the production gate, end to end."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import requires_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"
PROJECT_ID = "stage3clitest"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "rasm.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        timeout=600,
    )


@pytest.fixture()
def project() -> Path:
    pd = PROJECTS / PROJECT_ID
    if pd.exists():
        shutil.rmtree(pd)
    (pd / "script").mkdir(parents=True)
    (pd / "research").mkdir()
    (pd / "storyboard").mkdir()
    (pd / "assets").mkdir()
    asset = pd / "assets" / "a.jpg"
    asset.write_bytes(b"fake-image-bytes")
    graph = {"lang": "en", "hook": "Hello", "scenes": [{"id": 1, "narration": "Hello world.", "duration": 2.0}]}
    (pd / "script" / "scriptgraph.json").write_text(json.dumps(graph), encoding="utf-8")
    (pd / "research" / "research.json").write_text("{}", encoding="utf-8")
    try:
        yield pd
    finally:
        if pd.exists():
            shutil.rmtree(pd, ignore_errors=True)


def _plan_with_asset(pd: Path) -> None:
    plan = {
        "fps": {"num": 24, "den": 1},
        "canvas": [2560, 1440],
        "scenes": [
            {
                "id": 1,
                "duration": 2.0,
                "narration": "Hello",
                "needs": [],
                "assets_used": [],
                "elements": [{"type": "text", "text": "Hello", "rect": [0, 0, 800, 600]}],
            }
        ],
    }
    (pd / "storyboard" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")


@requires_ffmpeg
def test_cli_approval_workflow(project: Path):
    _plan_with_asset(project)
    init = _run("project", "init", PROJECT_ID)
    assert init.returncode == 0, init.stderr

    listing = _run("approvals", "list", PROJECT_ID, "--json")
    assert listing.returncode == 0, listing.stderr
    rows = json.loads(listing.stdout)
    assert rows == []  # no research assets imported yet

    # a pending asset blocks the final render
    pre = _run("render", PROJECT_ID, "--out", str(project / "render" / "pre.mp4"))
    assert pre.returncode == 0, pre.stdout + pre.stderr

    # register the asset through the research index and import it
    (project / "research" / "assets.json").write_text(
        json.dumps(
            [
                {
                    "path": "assets/a.jpg",
                    "sha256": "",
                    "kind": "photo",
                    "mime": "image/jpeg",
                    "source": "Wikimedia Commons",
                    "url": "https://example.invalid/a.jpg",
                    "page_url": "https://example.invalid/page",
                    "license": "CC0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "title": "A",
                    "author": "Tester",
                    "attr": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    imported = _run("approvals", "import", PROJECT_ID)
    assert imported.returncode == 0, imported.stderr

    rows = json.loads(_run("approvals", "list", PROJECT_ID, "--json").stdout)
    assert len(rows) == 1
    asset_id = rows[0]["asset_id"]
    assert rows[0]["state"] == "pending"

    # the plan now uses the asset, so the final render is refused
    plan = json.loads((project / "storyboard" / "plan.json").read_text(encoding="utf-8"))
    plan["scenes"][0]["assets_used"] = [str(project / "assets" / "a.jpg")]
    plan["scenes"][0]["elements"].append(
        # the picture must not sit under the text: the plan validator now
        # refuses a composition whose elements overlap (the gate under test
        # here is the **approval** gate, not the composition one)
        {"type": "image", "asset": str(project / "assets" / "a.jpg"), "rect": [900, 200, 600, 450]}
    )
    (project / "storyboard" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    _run("project", "migrate", PROJECT_ID, "--apply", "--force")

    out = project / "render" / "final.mp4"
    blocked = _run("render", PROJECT_ID, "--out", str(out))
    assert blocked.returncode == 2, blocked.stdout
    assert "asset-not-approved" in (blocked.stdout + blocked.stderr)
    assert not out.exists()

    # approving opens the gate for that asset
    approved = _run(
        "approvals", "approve", PROJECT_ID, "--asset", asset_id, "--by", "tester", "--note", "checked"
    )
    assert approved.returncode == 0, approved.stderr

    rows = json.loads(_run("approvals", "list", PROJECT_ID, "--json").stdout)
    assert rows[0]["state"] == "approved"
    assert rows[0]["reviewer"] == "tester"

    gate = _run("approvals", "gate", PROJECT_ID)
    assert gate.returncode == 0, gate.stdout + gate.stderr

    # the decision log is append-only and lives in the project
    log = (project / "research" / "approvals.jsonl").read_text(encoding="utf-8")
    assert log.count("\n") == 1
    assert '"decision": "approved"' in log
