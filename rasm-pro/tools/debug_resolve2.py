"""تشخيص المطابقة لعدة كيانات مع أنواعها الحقيقية (name:type)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from engine.core.config import load_config  # noqa: E402
from engine.research.http import HttpClient  # noqa: E402
from engine.research.wikipedia import Wikipedia  # noqa: E402
from engine.research.wikidata import Wikidata  # noqa: E402
from engine.stages.research import resolve_entity  # noqa: E402


def main() -> int:
    cfg = load_config()
    ua = cfg.get("research", "user_agent", default="rasm-pro/0.1 (whiteboard video engine; contact: local)")
    client = HttpClient(ua, timeout=int(cfg.get("research", "download_timeout", default=45)))
    wd = Wikidata(client)
    wiki = Wikipedia(client)

    pairs = sys.argv[1:] or [
        "ألمانيا:country",
        "بريطانيا:country",
        "الجنود:person",
        "الحرب:event",
        "فرنسا:country",
    ]
    dates = ["1914", "1917", "1919"]
    for p in pairs:
        name, _, typ = p.partition(":")
        typ = typ or "concept"
        ent = {"name": name, "type": typ, "context": "", "why": ""}
        out = resolve_entity(ent, wd=wd, wiki=wiki, cfg=cfg, script_dates=dates)
        f = out.get("facts") or {}
        w = out.get("wikipedia") or {}
        print(f"\n===== {name} ({typ}) =====")
        print(f"  facts : {f.get('qid')} | {f.get('label')} | {str(f.get('description'))[:80]}")
        print(f"  label_en: {f.get('label_en')} | iso2: {f.get('iso2')} | score: {f.get('match_score')}")
        print(f"  sitelinks: { {k: v for k, v in (f.get('sitelinks') or {}).items() if k in ('arwiki', 'enwiki')} }")
        print(f"  wiki  : {w.get('lang')} | {w.get('title')} | extract={len(w.get('extract') or '')} حرف")
        print(f"  query : {out.get('query_names')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
