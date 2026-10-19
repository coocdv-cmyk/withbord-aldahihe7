"""تشخيص مسار resolve_entity كاملًا لكيان شخص (خطوة خطوة)."""
from __future__ import annotations

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
from engine.stages.research import EXPECTED_TYPES, _name_overlap, _strip_title, resolve_entity  # noqa: E402

AVOID = ["اغتيال", "معركة", "حرب", "ثورة", "مذبحة", "انقلاب", "هجوم", "مؤتمر", "معاهدة", "اتفاقية", "قضية", "حادثة", "عملية", "حصار"]


def main() -> int:
    cfg = load_config()
    ua = cfg.get("research", "user_agent", default="rasm-pro/0.1 (whiteboard video engine; contact: local)")
    client = HttpClient(ua)
    wd = Wikidata(client)
    wiki = Wikipedia(client)

    for full in ("الأرشيدوق فرانز فرديناند",):
        stripped = _strip_title(full)
        print("stripped:", stripped)
        s = wiki.best_summary(stripped, avoid=AVOID)
        print("  best_summary:", (s or {}).get("lang"), "|", (s or {}).get("title"))
        if s:
            qid = wd.by_sitelink(s.get("lang", "ar"), s["title"])
            print("  by_sitelink:", qid)
            if qid:
                f = wd.facts(qid)
                print("  facts:", (f or {}).get("label"), "| years:", wd.facts_years(f or {}), "| life:", wd.life_span(f or {}))
                print("  overlap:", _name_overlap((f or {}).get("label") or "", stripped), _name_overlap(s["title"], stripped))

        ent = {"name": full, "type": "person", "context": "", "why": ""}
        print("  expected_types:", EXPECTED_TYPES.get("person"))
        print("  resolve_human:", end=" ")
        best = wd.resolve(full, context="", dates=["1914", "1917", "1919"], expected_types=EXPECTED_TYPES.get("person"), search_names=[stripped, full])
        print((best or {}).get("label"), "|", (best or {}).get("qid"), "|", (best or {}).get("match_score"))
        out = resolve_entity(ent, wd=wd, wiki=wiki, cfg=cfg, script_dates=["1914", "1917", "1919"])
        f2 = out.get("facts") or {}
        print("  النتيجة النهائية:", f2.get("label"), "|", f2.get("qid"), "| wikipedia:", (out.get("wikipedia") or {}).get("title"))
        print("  query_names:", out.get("query_names"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
