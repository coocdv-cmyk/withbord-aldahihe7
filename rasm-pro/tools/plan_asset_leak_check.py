"""قياس: هل تخرج الأصول المرفوضة من الخطة الجديدة — بلا عين بشرية؟

المقارنة: الأصول التي يستخدمها plan_v* مقابل قرارات الرفض في approvals.jsonl.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.core.util import read_json  # noqa: E402
from engine.stages.plan import build_plan  # noqa: E402


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "episode-02-art-of-war"
    pd = ROOT / "projects" / name
    graph = read_json(pd / "script" / "scriptgraph.json", default={}) or {}
    research = read_json(pd / "research" / "research.json", default={}) or {}
    decisions = []
    for line in (pd / "research" / "approvals.jsonl").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            decisions.append(json.loads(line))
    rejected = {
        str(r.get("path") or "") for r in decisions if r.get("decision") == "rejected"
    }
    approved = {
        str(r.get("path") or "") for r in decisions if r.get("decision") == "approved"
    }

    plan = build_plan(graph, research, project_dir=pd)
    used: set[str] = set()
    for scene in plan.get("scenes") or []:
        for path in scene.get("assets_used") or []:
            used.add(str(path).replace("\\", "/"))

    leak_rejected = sorted(used & rejected)
    used_approved = sorted(used & approved)
    print(f"· المشروع: {name}")
    print(f"· أصول مستخدمة في الخطة الجديدة: {len(used)}")
    print(f"· مرفوضة واعتمدتُها الخطة: {len(leak_rejected)}")
    for path in leak_rejected:
        print(f"   ✘ {path}")
    print(f"· معتمدة مني ودخلت الخطة: {len(used_approved)}")
    print(f"· قواعد الحجب: {plan.get('rejections', {}).get('rules')}")
    blocked = plan.get("rejections", {}).get("blocked") or []
    print(f"· أصول محجوبة بالقواعد: {len(blocked)}")
    for item in blocked[:12]:
        print(f"   · {str(item.get('title'))[:60]} — {(item.get('reason') or '')[:60]}")
    rel = plan.get("relevance") or {}
    print(f"· بوابة الملاءمة: حكمت {rel.get('judged')} · رفضت {rel.get('rejected')} · تحتاج عينًا {rel.get('needs_human')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
