"""العقد: ذاكرة الرفض تتعلّم من قراراتك وتمنع تكرارها.

المشكلة المقيسة: البحث يجد **بالاسم**، فيحلّف «قطارًا» لبلد و«سفينة حديثة»
لقائد من القرن السادس عشر. في حلقة «فن الحرب» رُفض 8 من 26 أصلًا بهذه
الطريقة — كل رفض يدوي درسٌ غير مكتوب.

هذه الاختبارات تثبت:
* القاعدة تُستنبط من **الأصول التي قرّرتها معتمدًا**: الرمز المشترك لا يُحجب.
* القاعدة **بنطاقها**: «ship» المرفوض لقائد لا تحجب خريطة.
* الأصل الذي يحمل الرمز **لا يدخل الخطة** — حتى لو لم يُرفض بالضبط.
* الأصل المعتمد لا يُحجب خطأً.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.memory.rejections import (
    RejectionRule,
    filter_assets,
    is_blocked,
    learn_rules,
    rules_for,
    save_rules,
)


def _write_decisions(project: Path, rows: list[dict]) -> None:
    (project / "research").mkdir(parents=True, exist_ok=True)
    (project / "research" / "approvals.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _write_assets(project: Path, assets: list[dict]) -> None:
    (project / "research").mkdir(parents=True, exist_ok=True)
    (project / "research" / "assets.json").write_text(
        json.dumps(assets, ensure_ascii=False), encoding="utf-8"
    )


def _asset(
    sha: str,
    title: str,
    path: str,
    entity: str = "X",
    need: str = "portrait",
    entity_type: str = "person",
) -> dict:
    return {
        "sha256": sha,
        "title": title,
        "path": path,
        "entity": entity,
        "entity_type": entity_type,
        "need": need,
    }


def test_a_rejection_teaches_a_rule_that_blocks_the_same_kind_of_asset(tmp_path: Path):
    project = tmp_path / "p"
    train = _asset("a" * 64, "File:Diesel locomotive ChME3 in Vinnitsa railway station.jpg", "assets/country-Ukraine/a.jpg", "Ukraine", "map", "country")
    book = _asset("b" * 64, "File:Eleven Commentaries to The Art of War.jpg", "assets/country-Japan/b.jpg", "Japan", "document", "country")
    _write_assets(project, [train, book])
    _write_decisions(
        project,
        [
            {"asset_id": "a-" + "a" * 12, "path": train["path"], "decision": "rejected", "note": "a train photograph does not depict the country"},
            {"asset_id": "a-" + "b" * 12, "path": book["path"], "decision": "approved", "note": "reviewed"},
        ],
    )
    rules = learn_rules(project)
    tokens = {r.token for r in rules}
    assert "locomotive" in tokens
    assert "railway" in tokens
    # the approved asset shares no distinctive token with the rejected one
    assert "commentaries" not in tokens

    # a NEW asset of the same kind is blocked without anyone rejecting it
    future = {"title": "File:Steam locomotive No. 7 at Kyiv railway station.jpg", "need": "map", "entity_type": "country"}
    blocked, reason = is_blocked(future["title"], rules, need="map", entity_type="country")
    assert blocked is True
    assert reason


def test_a_shared_token_is_never_blocked(tmp_path: Path):
    """«Japan» يظهر في أصل مرفوض وأصل معتمد ⇒ لا يُحجب (وإلّا خسرنا الأصول)."""
    project = tmp_path / "p"
    rejected = _asset("c" * 64, "File:Japan Relief Map of Land and Seabed.png", "assets/country-Japan/c.png", "Japan", "document", "country")
    approved = _asset("d" * 64, "File:Japan Map Chikei.gif", "assets/country-Japan/d.png", "Japan", "document", "country")
    _write_assets(project, [rejected, approved])
    _write_decisions(
        project,
        [
            {"asset_id": "a-" + "c" * 12, "path": rejected["path"], "decision": "rejected", "note": "a relief map, not the printed book"},
            {"asset_id": "a-" + "d" * 12, "path": approved["path"], "decision": "approved", "note": "reviewed"},
        ],
    )
    rules = learn_rules(project)
    tokens = {r.token for r in rules}
    assert "japan" not in tokens
    assert "map" not in tokens
    # but the distinctive token of the rejected title IS a rule
    assert "relief" in tokens or "seabed" in tokens


def test_a_rule_keeps_its_scope(tmp_path: Path):
    """«ship» المرفوض لقائد (portrait) لا يحجب خريطة (map)."""
    rule = RejectionRule(token="ship", entity_type="person", need="portrait", reason="a modern warship")
    blocked, _ = is_blocked("File:Some ship plan.jpg", [rule], need="map", entity_type="country")
    assert blocked is False
    blocked, _ = is_blocked("File:Some ship plan.jpg", [rule], need="portrait", entity_type="person")
    assert blocked is True


def test_the_filter_splits_allowed_from_blocked(tmp_path: Path):
    rules = [RejectionRule(token="locomotive", entity_type="country", need="map", reason="train photo")]
    assets = [
        {"title": "File:Diesel locomotive in Ukraine.jpg", "need": "map", "entity_type": "country"},
        {"title": "File:Map of Ukraine.svg", "need": "map", "entity_type": "country"},
    ]
    allowed, blocked = filter_assets(assets, rules)
    assert len(allowed) == 1
    assert len(blocked) == 1
    assert "locomotive" in blocked[0]["blocked_reason"]


def test_saved_rules_are_reused(tmp_path: Path):
    project = tmp_path / "p"
    (project / "research").mkdir(parents=True)
    rule = RejectionRule(token="chikei", entity_type="country", need="map", reason="low-res gif")
    save_rules(project, [rule])
    rules = rules_for(project)
    assert [r.token for r in rules] == ["chikei"]
