"""ذاكرة الرفض: تتعلّم من قراراتك البشرية وتُطبَّق على البحث القادم.

المشكلة المقيسة
----------------
البحث يجد **بالاسم**، فيُرجع «قطارًا» لبلد، و«سفينة حديثة» لقائد من القرن
السادس عشر، و«صفحة ترجمة» لشخصية. في حلقة «فن الحرب» رُفض **8 من 26**
أصلًا بهذه الطريقة بالضبط — كل رفض يدوي هو درس غير مكتوب.

ما تفعله هذه الوحدة
--------------------
من سجل قراراتك (``research/approvals.jsonl``) تستنبط **قواعد حجب**:
لكل أصل رفضته، رموزه **المميِّزة** (التي لا تظهر في أي أصلٍ قرّرته
«معتمد») تصبح 금지ًا: أي أصل يحملها لا يدخل الخطة.

الدقة شرط: الرمز المشترك (مثل «Japan» في أصول اليابان) لا يُحجب — وإلّا
خسرنا الأصول الصحيحة. ولذلك المقارنة تتم مع **الأصول التي أقرّتها أنت**،
لا مع كلام الموديل.

الحدّ الصريح: حالة «صفحة ترجمة فرنسية» لا تُستنبط منها قاعدة (عنوانها لا
يحمل رموزًا مميِّزة) — تبقى تحتاج عينًا أو نموذج رؤية.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..core.log import get_logger

log = get_logger("memory.rejections")

RULES_FILE = "rejections.jsonl"

# رموز لا تُحجب (وظيفية أو شائعة جدًا)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MIN_LEN = 4  # رمز أقصر من أربعة أحرف لا يُحجب (SUN / ZI / 51)

_NEVER_BLOCK = {
    "file", "image", "photo", "commons", "wikipedia", "jpg", "jpeg", "png",
    "svg", "gif", "tif", "tiff", "webp", "djvu",
    # كلمات شائعة في العناوين تُستخدم في سياقات لا صلة لها — حاجبها يُسقط
    # أصولًا سليمة
    "land", "view", "page", "pages", "cover", "edition", "volume", "vol",
    "printed", "scan", "archive", "library", "university", "museum",
    "collection", "series", "version", "translation", "english", "french",
    "german", "arabic", "latin", "world", "history", "book", "books",
}


@dataclass
class RejectionRule:
    """قاعدة حجب: رمز في العنوان لا يُستخدم لهذا النوع/الاحتياج."""

    token: str
    entity_type: str = ""
    need: str = ""
    reason: str = ""
    added: str = ""
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RejectionRule":
        return cls(
            token=str(d.get("token") or ""),
            entity_type=str(d.get("entity_type") or ""),
            need=str(d.get("need") or ""),
            reason=str(d.get("reason") or ""),
            added=str(d.get("added") or ""),
            sources=list(d.get("sources") or []),
        )


def _tokens(title: str) -> set[str]:
    out: set[str] = set()
    for raw in _TOKEN_RE.findall(str(title or "").lower()):
        if len(raw) < _MIN_LEN:
            continue
        if raw in _NEVER_BLOCK:
            continue
        out.add(raw)
    return out


def _decisions(project_dir: str | Path) -> list[dict]:
    path = Path(project_dir) / "research" / "approvals.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return rows


def _assets_by_id(project_dir: str | Path) -> dict[str, dict]:
    """خريطة asset_id/path → سجل الأصل (بما فيه العنوان)."""
    from ..core.util import read_json

    pd = Path(project_dir)
    out: dict[str, dict] = {}
    for rec in read_json(pd / "research" / "assets.json", default=[]) or []:
        if not isinstance(rec, dict):
            continue
        sha = str(rec.get("sha256") or "")
        if sha:
            out["a-" + sha[:12]] = rec
        path = str(rec.get("path") or "")
        if path:
            out[path] = rec
    # research.json قد يحمل نفس الأصول بشكل آخر
    research = read_json(pd / "research" / "research.json", default={}) or {}
    for ent in research.get("entities") or []:
        for item in ent.get("assets") or []:
            rec = item.get("asset") or {}
            if not isinstance(rec, dict):
                continue
            sha = str(rec.get("sha256") or "")
            if sha:
                out.setdefault("a-" + sha[:12], rec)
            path = str(rec.get("path") or "")
            if path:
                out.setdefault(path, rec)
    return out


def learn_rules(project_dir: str | Path) -> list[RejectionRule]:
    """يستنبط قواعد الحجب من قرارات هذا المشروع.

    القاعدة: الرمز المميِّز لعنوانٍ مرفوض = رمز في العنوان لا يظهر في **أي**
    عنوان معتمد.  هكذا نمنع «locomotive» و«railway» دون أن نمنع «Japan».
    """
    pd = Path(project_dir)
    decisions = _decisions(pd)
    assets = _assets_by_id(pd)
    if not decisions:
        return []

    approved_tokens: set[str] = set()
    rejected: list[dict] = []
    for row in decisions:
        decision = str(row.get("decision") or "").lower()
        key = str(row.get("asset_id") or row.get("path") or "")
        rec = assets.get(key) or assets.get(str(row.get("path") or "")) or {}
        title = str(rec.get("title") or row.get("title") or "")
        if decision == "rejected":
            rejected.append(
                {
                    "title": title,
                    "reason": str(row.get("note") or ""),
                    "entity_type": str(rec.get("entity_type") or ""),
                    "need": str(rec.get("need") or ""),
                    "source": key,
                }
            )
        elif decision == "approved":
            approved_tokens |= _tokens(title)

    rules: dict[str, RejectionRule] = {}
    for item in rejected:
        for token in sorted(_tokens(item["title"]) - approved_tokens):
            rule = rules.get(token)
            if rule is None:
                rules[token] = RejectionRule(
                    token=token,
                    entity_type=item["entity_type"],
                    need=item["need"],
                    reason=item["reason"],
                    added=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    sources=[item["source"]] if item["source"] else [],
                )
            else:
                if item["source"] and item["source"] not in rule.sources:
                    rule.sources.append(item["source"])
    return sorted(rules.values(), key=lambda r: r.token)


def save_rules(project_dir: str | Path, rules: Iterable[RejectionRule]) -> Path:
    """يكتب القواعد في ``memory/rejections.jsonl`` (append آمن)."""
    pd = Path(project_dir)
    path = pd / "memory" / RULES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rule in rules:
            f.write(json.dumps(rule.to_dict(), ensure_ascii=False) + "\n")
    return path


def load_rules(project_dir: str | Path) -> list[RejectionRule]:
    path = Path(project_dir) / "memory" / RULES_FILE
    if not path.exists():
        return []
    out: list[RejectionRule] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(RejectionRule.from_dict(json.loads(line)))
            except Exception:
                continue
    except Exception:
        return []
    return out


def rules_for(project_dir: str | Path) -> list[RejectionRule]:
    """القواعد المحفوظة، وإن لم توجد تُستنبط من قرارات المشروع."""
    saved = load_rules(project_dir)
    if saved:
        return saved
    return learn_rules(project_dir)


def blocked_titles(rules: Iterable[RejectionRule]) -> dict[str, list[str]]:
    """خريطة: الرمز → قائمة القواعد التي تمنعه."""
    out: dict[str, list[str]] = {}
    for rule in rules:
        out.setdefault(rule.token.lower(), []).append(rule.reason or rule.token)
    return out


def is_blocked(
    title: str,
    rules: Iterable[RejectionRule],
    *,
    need: str = "",
    entity_type: str = "",
) -> tuple[bool, str]:
    """هل يمنع هذا العنوان؟ يعيد (ممنوع، السبب).

    **النطاق**: القاعدة تخصّ احتياجًا ونوعًا معيّنين.  رمز مثل «ship» مُرفض
    لقائد (portrait) لا يُحجب خريطة (map) — نفس الكلمة في سياق آخر ليست
    نفس الدلالة.
    """
    tokens = _tokens(title)
    for rule in rules:
        if rule.token.lower() not in tokens:
            continue
        if rule.need and need and rule.need != need:
            continue
        if rule.entity_type and entity_type and rule.entity_type != entity_type:
            continue
        return True, f"قاعدة حاجب «{rule.token}»: {rule.reason}" if rule.reason else f"قاعدة حاجب: {rule.token}"
    return False, ""


def filter_assets(
    assets: list[dict],
    rules: Iterable[RejectionRule],
) -> tuple[list[dict], list[dict]]:
    """يفصل الأصول المسموحة عن المحجوبة. يعيد (المسموح، المحجوب+السبب)."""
    rules = list(rules)
    allowed: list[dict] = []
    blocked: list[dict] = []
    for asset in assets:
        title = str(asset.get("title") or "")
        is_blocked_, reason = is_blocked(
            title,
            rules,
            need=str(asset.get("need") or ""),
            entity_type=str(asset.get("entity_type") or ""),
        )
        if is_blocked_:
            blocked.append({**asset, "blocked_reason": reason})
        else:
            allowed.append(asset)
    return allowed, blocked


__all__ = [
    "RejectionRule",
    "blocked_titles",
    "filter_assets",
    "is_blocked",
    "learn_rules",
    "load_rules",
    "rules_for",
    "save_rules",
]
