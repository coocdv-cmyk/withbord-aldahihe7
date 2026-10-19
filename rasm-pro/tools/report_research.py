"""تقرير سريع لنتائج البحث (research.json) — للعرض والمراجعة."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "projects" / "ww1" / "research" / "research.json"
data = json.loads(path.read_text(encoding="utf-8"))

print(f"التقرير: {path}")
print(f"إجماليات: {data.get('totals')}")
print()

for e in data.get("entities", []):
    facts = e.get("facts") or {}
    mark = "✓" if facts else "—"
    label = facts.get("label") or ""
    desc = (facts.get("description") or "")[:70]
    print(f"[{e['type']}] {e['name']}  (wikidata: {mark} {label} — {desc})")
    if e.get("wikipedia"):
        print(f"    سياق: {e['wikipedia'][:120].strip()}...")
    for a in e.get("assets", []):
        r = a.get("asset") or a.get("candidate") or {}
        title = (r.get("title") or r.get("path") or "")[:76]
        lic = r.get("license") or "?"
        author = (r.get("author") or "")[:36]
        size = f"{r.get('width')}x{r.get('height')}" if r.get("width") else ""
        tag = "↺" if r.get("reused") else "+"
        print(f"   {tag} {title} | {lic} | {author} | {size}")
        print(f"      path: {r.get('path')}")
    if not e.get("assets"):
        print("   (لا أصول)")
    print()

print("--- مرفوض (بوابة الترخيص/الجودة) ---")
for s in data.get("skipped", [])[:12]:
    print(f"  x [{s.get('need')}] {str(s.get('title'))[:60]} | {str(s.get('why'))[:90]}")
