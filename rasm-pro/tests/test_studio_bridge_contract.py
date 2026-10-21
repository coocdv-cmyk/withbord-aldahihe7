"""Regression: the Studio bridge must use the **same** production contract.

Stage 6 replaced two drifting paths (CLI and Studio) with one shared module
(``engine/production.py``).  Nothing pinned that down: the bridge could have
gone back to calling the Director directly and every test would still pass.

These tests pin the delegation itself — if the bridge stops routing through
``engine.production``, the sentinel test fails.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BRIDGE_PATH = REPO / "studio" / "rasm_bridge.py"


def _load_bridge():
    spec = importlib.util.spec_from_file_location("rasm_bridge_contract", BRIDGE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bridge():
    return _load_bridge()


def _plan() -> dict:
    return {
        "fps": {"num": 24, "den": 1},
        "canvas": [2560, 1440],
        "lang": "ar",
        "scenes": [
            {
                "id": 1,
                "duration": 1.0,
                "start_frame": 0,
                "end_frame": 24,
                "duration_frames": 24,
                "elements": [],
            }
        ],
    }


def test_the_bridge_loads_the_engine(bridge):
    assert bridge.RASM_AVAILABLE is True, bridge._RASM_ERROR


def test_the_bridge_refuses_when_there_is_no_plan(bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(bridge.rasm_paths, "PROJECTS", tmp_path / "projects")
    with pytest.raises(RuntimeError) as excinfo:
        bridge.render_project_studio("nothing-here", mode="final")
    assert "plan" in str(excinfo.value).lower()


def test_the_bridge_delegates_to_the_shared_production_contract(
    bridge, tmp_path, monkeypatch
):
    """The bridge must go through ``engine.production`` — not the Director."""
    import engine.production as production

    projects = tmp_path / "projects"
    pd = projects / "demo"
    (pd / "storyboard").mkdir(parents=True)
    (pd / "storyboard" / "plan.json").write_text(
        json.dumps(_plan(), ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(bridge.rasm_paths, "PROJECTS", projects)

    sentinel = RuntimeError("sentinel: the shared contract was called")

    def _boom(*args, **kwargs):
        raise sentinel

    monkeypatch.setattr(production, "prepare_production", _boom)
    with pytest.raises(RuntimeError) as excinfo:
        bridge.render_project_studio("demo", mode="final")
    assert "sentinel" in str(excinfo.value)
