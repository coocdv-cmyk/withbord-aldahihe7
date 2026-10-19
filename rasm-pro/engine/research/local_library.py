"""مكتبة الأيقونات المحلية (318 ألف أصل) — بحث بالكلمات عن أصول SVG جاهزة للرسم.

تبني فهرسًا مخزّنًا (مرة واحدة) من library/manifest-icons.jsonl.
"""
from __future__ import annotations

from ..core.paths import LIBRARY, cache_file
from ..core.util import read_json, write_json

INDEX_FILE = "icons-index.json"
MANIFEST = LIBRARY / "manifest-icons.jsonl"
SVG_DIR = LIBRARY / "svg"

PREFERRED_SETS = ("lucide", "tabler", "ph", "mdi", "solar", "carbon", "heroicons", "iconoir", "fluent", "material-symbols")


def _iter_manifest():
    if not MANIFEST.exists():
        return
    with open(MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                import json

                yield json.loads(line)
            except Exception:
                continue


def build_index(force: bool = False, max_per_token: int = 40) -> dict:
    """فهرس توكن → أصول (خطوط فقط + ثقة core أولًا)."""
    cache = cache_file("library", INDEX_FILE)
    if cache.exists() and not force:
        return read_json(cache, default={})

    # مجموعة الملفات الموجودة فعلًا (52 ألف SVG) — مرة واحدة
    existing: set[str] = set()
    if SVG_DIR.exists():
        for p in SVG_DIR.rglob("*.svg"):
            existing.add(p.relative_to(SVG_DIR).as_posix().lower())
            existing.add(p.name.lower())

    def resolve_file(rec: dict) -> str | None:
        raw = rec.get("file")
        if raw:
            rel = str(raw).replace("\\", "/")
            if rel.lower().startswith("svg/"):
                rel = rel[4:]
            if rel.lower() in existing:
                return str((SVG_DIR / rel).resolve())
            base = rel.split("/")[-1].lower()
            if base in existing:
                for p in SVG_DIR.rglob(rel.split("/")[-1]):
                    return str(p)
        prefix = rec.get("prefix", "")
        name = rec.get("name", "")
        cand = f"{prefix}/{name}.svg".lower()
        if cand in existing:
            return str((SVG_DIR / prefix / f"{name}.svg").resolve())
        cand2 = f"{name}.svg".lower()
        if cand2 in existing:
            for p in SVG_DIR.rglob(f"{name}.svg"):
                if p.parent.name == prefix:
                    return str(p)
        return None

    index: dict[str, list[dict]] = {}
    count = 0
    for rec in _iter_manifest():
        file_path = resolve_file(rec)
        if not file_path:
            continue
        name = (rec.get("name") or "").lower()
        tokens = [t for t in name.replace("_", "-").split("-") if len(t) > 2 and not t.isdigit()]
        if not tokens:
            continue
        entry = {
            "id": rec.get("id"),
            "name": name,
            "set": rec.get("prefix"),
            "style": rec.get("style"),
            "trust": rec.get("trust"),
            "license": rec.get("license"),
            "attr": rec.get("attrRequired"),
            "file": file_path,
        }
        for t in set(tokens):
            bucket = index.setdefault(t, [])
            if len(bucket) < max_per_token:
                bucket.append(entry)
        count += 1
    write_json(cache, index, indent=None)
    return index


def search_icons(keywords: list[str], *, limit: int = 8, prefer_line: bool = True) -> list[dict]:
    """بحث محلي بالأيقونات (تطابق توكنات) مع تفضيل مجموعات موثوقة وخطية."""
    index = build_index()
    seen: dict[str, dict] = {}
    for kw in keywords:
        for token in str(kw).lower().replace("_", "-").split("-"):
            for entry in index.get(token, []):
                eid = entry["id"]
                if eid in seen:
                    seen[eid]["score"] += 1
                else:
                    e = dict(entry)
                    e["score"] = 1
                    seen[eid] = e

    def sort_key(e: dict):
        trust = 0 if e.get("trust") == "core" else 1
        style = 0 if (prefer_line and e.get("style") == "stroke") else (1 if e.get("style") in ("stroke", None) else 2)
        pref = PREFERRED_SETS.index(e["set"]) if e.get("set") in PREFERRED_SETS else 99
        return (trust, style, pref, -e["score"], e.get("name") or "")

    return sorted(seen.values(), key=sort_key)[:limit]
