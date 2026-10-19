"""عرض مختصر لمخطط السكريبت (كيانات + مشاهد)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

rel = sys.argv[1] if len(sys.argv) > 1 else "projects/ww1-llm/script/scriptgraph.json"
g = json.loads((ROOT / rel).read_text(encoding="utf-8"))
print("hook:", g.get("hook"))
print("engine:", g.get("engine"), "| lang:", g.get("lang"), "| scenes:", len(g.get("scenes", [])))
print("--- كيانات")
for e in g.get("entities", []):
    ctx = str(e.get("context") or "")
    print(f"{e.get('name'):35s} {str(e.get('type')):8s} needs={e.get('needs')} ctx={ctx[:70]}")
print("--- مشاهد")
for s in g.get("scenes", []):
    print(f"[{s.get('id')}] {str(s.get('narration'))[:90]}")
    ents = s.get("entities") or []
    if ents:
        print("     كيانات:", ", ".join(x if isinstance(x, str) else str(x.get("name")) for x in ents))
    for c in (s.get("claims") or [])[:3]:
        print("     ادّعاء:", str(c)[:110])
