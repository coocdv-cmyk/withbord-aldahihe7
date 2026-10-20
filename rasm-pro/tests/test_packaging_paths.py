from __future__ import annotations

import json
from pathlib import Path

import engine.assets.style as style_mod
from engine.core import paths


def test_source_tree_ships_the_default_style_pack():
    """The pack must exist in the bundle, not only in the writable data dir."""
    assert (paths.BUNDLE_STYLE_PACKS / "paper_ink_v1.json").is_file()


def test_style_pack_falls_back_to_the_bundle(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle" / "style_packs"
    bundle.mkdir(parents=True)
    (bundle / "paper_ink_v1.json").write_text(
        json.dumps({"kinds": {"photo": []}}), encoding="utf-8"
    )
    monkeypatch.setattr(style_mod, "STYLE_PACKS", tmp_path / "data" / "style_packs")
    monkeypatch.setattr(style_mod, "BUNDLE_STYLE_PACKS", bundle)

    data = style_mod.load_style()

    assert data["id"] == "paper_ink_v1"
    assert data["_path"] == str(bundle / "paper_ink_v1.json")


def test_missing_style_pack_reports_both_locations(tmp_path, monkeypatch):
    monkeypatch.setattr(style_mod, "STYLE_PACKS", tmp_path / "data" / "style_packs")
    monkeypatch.setattr(style_mod, "BUNDLE_STYLE_PACKS", tmp_path / "bundle" / "style_packs")

    try:
        style_mod.load_style("nope_v9")
    except FileNotFoundError as exc:
        message = str(exc)
        assert "nope_v9.json" in message
        assert "bundle" in message
    else:  # pragma: no cover - the loader must raise
        raise AssertionError("missing style pack must raise FileNotFoundError")


def test_data_root_follows_rasm_home(monkeypatch, tmp_path):
    monkeypatch.setenv("RASM_HOME", str(tmp_path))
    import importlib

    reloaded = importlib.reload(paths)
    try:
        assert reloaded.ROOT == tmp_path.resolve()
        assert reloaded.PROJECTS == tmp_path.resolve() / "projects"
        # Read-only assets stay inside the bundle (or the source tree).
        assert reloaded.ASSETS == reloaded.BUNDLE / "assets"
    finally:
        monkeypatch.delenv("RASM_HOME", raising=False)
        importlib.reload(paths)
