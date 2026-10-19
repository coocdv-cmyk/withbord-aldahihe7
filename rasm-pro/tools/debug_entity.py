"""تشخيص تفصيلي لكيان واحد: ويكي بيانات + ويكيبيديا + المرشحون ودرجاتهم."""
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

AVOID = ["اغتيال", "معركة", "حرب", "ثورة", "مذبحة", "انقلاب", "هجوم", "مؤتمر", "معاهدة", "اتفاقية", "قضية", "حادثة", "عملية", "حصار"]


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "فرانز فرديناند"
    cfg = load_config()
    ua = cfg.get("research", "user_agent", default="rasm-pro/0.1 (whiteboard video engine; contact: local)")
    client = HttpClient(ua)
    wd = Wikidata(client)
    wiki = Wikipedia(client)

    for lang in ("ar", "en"):
        print(f"--- بحث ويكيبيديا ({lang}): {name}")
        for h in wiki.search(name, lang=lang, limit=6):
            print(f"   · {h['title']}  (كلمات: {h['wordcount']})")
    s = wiki.best_summary(name, avoid=AVOID)
    print("best_summary(avoid):", (s or {}).get("lang"), (s or {}).get("title"))

    hits = wd.search_entity_multi(name)
    print(f"--- ويكي بيانات: {len(hits)} نتيجة")
    for h in hits[:6]:
        f = wd.facts(h["qid"]) or {}
        inst = f.get("instance_of") or []
        print(f"   · {h['qid']} | {h.get('label')} | {(h.get('description') or '')[:70]}")
        print(f"      instance_of={inst} years={wd.facts_years(f)} life={wd.life_span(f)}")

    best = wd.resolve(name, dates=["1914", "1917", "1919"], expected_types=["human"], search_names=[name])
    print("--- resolve (human):")
    if best:
        print(json.dumps(best.get("candidates"), ensure_ascii=False, indent=1))
        print("  qid:", best.get("qid"), "| label:", best.get("label"), "| score:", best.get("match_score"))
    else:
        print("  None")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
