"""تشخيص مطابقة الكيانات خطوة بخطوة (يستخدم الكاش — بلا طلبات جديدة)."""
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
from engine.stages.research import resolve_entity  # noqa: E402


def main() -> int:
    cfg = load_config()
    ua = cfg.get("research", "user_agent", default="rasm-pro/0.1 (whiteboard video engine; contact: local)")
    client = HttpClient(ua, timeout=int(cfg.get("research", "download_timeout", default=45)))
    wd = Wikidata(client)
    wiki = Wikipedia(client)
    names = sys.argv[1:] or ["الأرشيدوق فرانز فرديناند", "معاهدة فرساي"]
    dates = ["1914", "1917", "1919"]
    for name in names:
        print(f"\n===== {name} =====")
        s = wiki.best_summary(name)
        print("best_summary:", (s or {}).get("lang"), "|", (s or {}).get("title"))
        if s:
            qid = wd.by_sitelink(s.get("lang", "ar"), s.get("title", ""))
            print("  sitelink qid:", qid)
            if qid:
                f = wd.facts(qid)
                if f:
                    print("  facts:", f.get("label"), "|", f.get("label_en"), "|", str(f.get("description"))[:80])
                    print("  years:", wd.facts_years(f), "life_span:", wd.life_span(f))
        ents = [
            {"name": name, "type": "person" if "فرديناند" in name else "event", "context": "", "why": ""},
        ]
        out = resolve_entity(ents[0], wd=wd, wiki=wiki, cfg=cfg, script_dates=dates)
        f = out.get("facts") or {}
        print("  النتيجة:", f.get("label"), "| qid:", f.get("qid"), "| score:", f.get("match_score"))
        print("  ويكيبيديا:", (out.get("wikipedia") or {}).get("title"))
        print("  أسماء بحث:", out.get("query_names"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
