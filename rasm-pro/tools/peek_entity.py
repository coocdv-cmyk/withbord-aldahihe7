"""نظرة سريعة: كيان معيّن من research.json (حقائق + أصول + مرفوض)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

rel = sys.argv[1] if len(sys.argv) > 1 else "projects/ww1-llm/research/research.json"
data = json.loads((ROOT / rel).read_text(encoding="utf-8"))
want = sys.argv[2:] or None
print("== إجماليات:", data.get("totals"))
for e in data.get("entities", []):
    name = e.get("name", "")
    if want and not any(w in name for w in want):
        continue
    f = e.get("facts") or {}
    wiki = e.get("wikipedia") if isinstance(e.get("wikipedia"), dict) else {}
    print(f"\n[{name}] type={e.get('type')} needs={e.get('needs')}")
    print(f"   wikidata: {f.get('qid')} | {f.get('label')} | {str(f.get('description'))[:70]}")
    print(f"   wikipedia: {wiki.get('lang')} | {wiki.get('title')}")
    print(f"   query_names: {e.get('query_names')}")
    print(f"   أصول: {len(e.get('assets') or [])} · مرفوض: {len(e.get('denied') or [])}")
    for a in e.get("assets", []):
        rec = a.get("asset") or {}
        print(f"     + [{rec.get('need')}] {str(rec.get('title'))[:70]} | {rec.get('license')} | {rec.get('path')}")
    for d in e.get("denied", [])[:6]:
        print(f"     x [{d.get('need')}] {str(d.get('title'))[:60]} | {d.get('reason')}")
