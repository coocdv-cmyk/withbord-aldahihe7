"""قياس بوابة الملاءمة على أحكام_EXTENSION البشري — لا على انطباع.

المصدر: ``research/approvals.jsonl`` (قراراتك: approved/rejected + سبب كل قرار)
و ``research/assets.json`` (الأصول التي دخلت المشروع) و ``script/scriptgraph.json``
(سياق الكيان: لماذا نحتاجه).

المقياس: هل تُمسك البوابة بالأصول التي رفضتها بالعين؟ وكم originals.aprobada
تسقط خطأً؟

الاستخدام:
    .venv\\Scripts\\python.exe tools\\relevance_report.py projects\\episode-02-art-of-war
    .venv\\Scripts\\python.exe tools\\relevance_report.py <project> --llm
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.core.util import read_json  # noqa: E402
from engine.research.relevance import judge_candidates  # noqa: E402


def _scene_context(graph: dict, entity: str) -> str:
    """أول مشهد يذكر الكيان — سياق المعنى الذي يحتاجه الأصل."""
    name = (entity or "").strip().lower()
    if not name:
        return ""
    for scene in graph.get("scenes") or []:
        text = str(scene.get("narration") or "")
        if name and name in text.lower():
            return text
    return ""


def _why_context(graph: dict, entity: str) -> str:
    for ent in graph.get("entities") or []:
        if str(ent.get("name") or "").strip().lower() == (entity or "").strip().lower():
            return str(ent.get("why") or "")
    return ""


def _from_path(path: str) -> tuple[str, str, str]:
    """يستنبط (النوع، الاسم، الاحتياج) من مسار الأصل.

    الأصل القديم لا يحمل بيانات وصفية كاملة، لكن المسار يحملها:
    ``assets/person-Sun-Tzu/148af13c6ddc.svg`` ⇒ نوع=person · اسم=Sun Tzu.
    """
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p]
    if len(parts) < 2 or parts[0] != "assets":
        return "", "", ""
    folder = parts[1]
    kind, _, name = folder.partition("-")
    need = {
        "person": "portrait",
        "country": "document",
        "concept": "document",
        "event": "event",
        "organization": "document",
        "place": "map",
    }.get(kind.lower(), "")
    return kind, name, need


def main() -> int:
    ap = argparse.ArgumentParser(description="تقرير ملاءمة الأصول مقابل الأحكام البشرية")
    ap.add_argument("project")
    ap.add_argument("--llm", action="store_true", help="استخدم الحكم الدلالي بالموديل المحلي")
    ap.add_argument("--json", action="store_true", help="أخرج JSON")
    args = ap.parse_args()

    pd = Path(args.project)
    if not pd.is_absolute():
        pd = ROOT / "projects" / args.project if not pd.exists() else pd
    if not pd.exists():
        print(f"✘ لا يوجد مشروع: {pd}")
        return 2

    research = read_json(pd / "research" / "research.json", default={}) or {}
    graph = read_json(pd / "script" / "scriptgraph.json", default={}) or {}
    approvals: list[dict] = []
    approvals_path = pd / "research" / "approvals.jsonl"
    if approvals_path.exists():
        for line in approvals_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                approvals.append(json.loads(line))
            except Exception:
                continue

    # خريطة: asset_id / path -> القرار البشري
    labels: dict[str, str] = {}
    notes: dict[str, str] = {}
    for row in approvals:
        key = str(row.get("asset_id") or row.get("path") or "")
        if not key:
            continue
        labels[key] = str(row.get("decision") or "")
        notes[key] = str(row.get("note") or "")
        if row.get("path"):
            labels[str(row["path"])] = str(row.get("decision") or "")

    # الأصول المخزّنة مع بياناتها
    assets = read_json(pd / "research" / "assets.json", default=[]) or []
    if not assets:
        for ent in research.get("entities") or []:
            for item in ent.get("assets") or []:
                rec = item.get("asset") or item.get("candidate") or {}
                if rec:
                    assets.append(rec)

    groups: list[dict] = []
    rows: list[dict] = []
    by_group: dict[tuple, list[dict]] = {}
    for rec in assets:
        entity = str(rec.get("entity") or "")
        need = str(rec.get("need") or "")
        entity_type = str(rec.get("entity_type") or "")
        sha = str(rec.get("sha256") or "")
        asset_id = "a-" + sha[:12] if sha else ""
        path = str(rec.get("path") or "")
        label = labels.get(asset_id) or labels.get(path) or ""
        if not label:
            continue
        # البيانات الوصفية الناقصة تُستنبط من المسار (بلا اختراع)
        if not entity or not need:
            p_kind, p_name, p_need = _from_path(path)
            entity = entity or p_name
            need = need or p_need
            entity_type = entity_type or p_kind
        context = {
            "name": entity,
            "type": entity_type,
            "need": need,
            "why": _why_context(graph, entity),
            "scene": _scene_context(graph, entity),
        }
        candidate = {
            "id": asset_id or path,
            "title": rec.get("title") or "",
            "mime": rec.get("mime") or "",
            "type": need,
        }
        era = rec.get("era")
        row = {
            "asset_id": asset_id,
            "title": rec.get("title") or "",
            "entity": entity,
            "need": need,
            "human": label,
            "era": int(era) if era else None,
            "human_note": notes.get(asset_id) or notes.get(path) or "",
        }
        rows.append(row)
        by_group.setdefault((entity, need), []).append((row, candidate, context))

    # حكم كل مجموعة في نداء واحد (الموديل يرى المرشّحين معًا)
    for (entity, need), items in by_group.items():
        context = items[0][2]
        candidates = [cand for _, cand, _ in items]
        verdicts = judge_candidates(
            candidates,
            context,
            era_year=items[0][0].get("era"),
            use_llm=args.llm,
        )
        for (row, cand, _), verdict in zip(items, verdicts):
            row["gate"] = verdict.verdict
            row["score"] = verdict.score
            row["reason"] = verdict.reason
            row["judge"] = verdict.judge

    if not rows:
        print("✘ لا توجد أصول لها حكم بشري — لا قياس.")
        return 2

    tp = sum(1 for r in rows if r["human"] == "rejected" and r["gate"] == "irrelevant")
    fn = sum(1 for r in rows if r["human"] == "rejected" and r["gate"] != "irrelevant")
    fp = sum(1 for r in rows if r["human"] != "rejected" and r["gate"] == "irrelevant")
    tn = sum(1 for r in rows if r["human"] != "rejected" and r["gate"] != "irrelevant")
    caught = [r for r in rows if r["human"] == "rejected" and r["gate"] == "irrelevant"]
    missed = [r for r in rows if r["human"] == "rejected" and r["gate"] != "irrelevant"]
    wrongly = [r for r in rows if r["human"] != "rejected" and r["gate"] == "irrelevant"]

    report = {
        "project": str(pd),
        "judge": "llm+heuristic" if args.llm else "heuristic",
        "labeled": len(rows),
        "human_rejected": tp + fn,
        "human_kept": fp + tn,
        "caught": tp,
        "missed": fn,
        "wrongly_dropped": fp,
        "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
        "recall": round(tp / (tp + fn), 3) if (tp + fn) else None,
        "rows": rows,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"· المشروع: {pd.name} · القاضي: {report['judge']} · معنون: {len(rows)}")
    print(
        f"· رفض بشري: {report['human_rejected']} · أبقى بشري: {report['human_kept']}"
    )
    print(
        f"· مُمسَك: {tp} · فائت: {fn} · مطروح خطأً: {fp} · "
        f"دقّة={report['precision']} استرجاع={report['recall']}"
    )
    if caught:
        print("\n✔ مُمسَك (رفض بشري ⇒ البوابة ترفض):")
        for r in caught:
            print(f"   - {r['title'][:70]} · {r['entity']} · {r['reason'][:70]}")
    if missed:
        print("\n✘ فائت (رُفض بالعين ودخل المشروع):")
        for r in missed:
            print(f"   - {r['title'][:70]} · {r['entity']} · {r['reason'][:70]}")
    if wrongly:
        print("\n⚠ مطروح خطأً (أُقرّ بالعين ورفضته البوابة):")
        for r in wrongly:
            print(f"   - {r['title'][:70]} · {r['entity']} · {r['reason'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
