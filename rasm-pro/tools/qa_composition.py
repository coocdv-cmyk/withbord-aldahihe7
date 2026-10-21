"""فحص تركيب آلي لكل مشهد — «الجودة» رقم لا إحساس.

الأداة غلافٌ رقيق فوق ``engine/render/validate_composition.py`` (نفس
الفحص الذي يرفض به المحرك خطة معطوبة قبل الرندر).

ما يقيسه لكل مشهد في الخطة:

* **التداخل**: هل يركب عنصرٌ فوق آخر (نصٌ فوق صورة، نصٌ فوق نص)؟ يُقاس
  بالهندسة **المرسومة** (نفس مقياس الرندر) لا بالمستطيل المعلَن.
* **حجم النص الفعلي**: النص الذي لا يسع صندوقه يُصغَّر — وهنا يُقاس كم
  صار صغيرًا، وهل بلغ حدّ القراءة.
* **فراغ المشهد**: مشهد بلا نص وبلا صورة = لقطة ميتة.
* **التكرار**: مشهدان متتاليان بنفس التوقيع (نفس الأدوار ونفس المخطط).
* **سعة الرسم**: هل النص المرسوم يسع زمن المشهد؟

الاستعمال::

    .venv\\Scripts\\python.exe tools\\qa_composition.py <project> [--plan PATH]

يكتب ``qa/<project>/composition.json`` ويخرج برمز ≠ 0 عند وجود عيب حاصر.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.core.paths import PROJECTS  # noqa: E402
from engine.core.util import read_json, write_json  # noqa: E402
from engine.render.validate_composition import validate_composition  # noqa: E402

PLAN_NAMES = (
    "plan_v8.json",
    "plan_v7.json",
    "plan_v6.json",
    "plan_v5.json",
    "plan_v4.json",
    "plan_v3.json",
    "plan_v2.json",
    "plan.json",
)


def find_plan(project_dir: Path, explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None
    # the **active** plan of the project wins over any numbered sibling
    manifest = project_dir / "project.json"
    if manifest.exists():
        try:
            data = read_json(manifest) or {}
            active = str((data.get("storyboard") or {}).get("active") or "")
            if active:
                candidate = project_dir / active
                if candidate.exists():
                    return candidate
        except Exception:
            pass
    for name in PLAN_NAMES:
        candidate = project_dir / "storyboard" / name
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="composition QA for a plan")
    ap.add_argument("project")
    ap.add_argument("--plan", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="قبول التحذيرات كأخطاء (بوابة القبول: لا مشهد فارغ ولا تكرار)",
    )
    args = ap.parse_args()

    pd = PROJECTS / args.project
    plan_path = find_plan(pd, args.plan)
    if plan_path is None:
        print(f"no plan found for {args.project}", file=sys.stderr)
        return 2
    plan = read_json(plan_path)
    report = validate_composition(plan)
    blocking = list(report.get("blocking") or [])
    warnings = list(report.get("warnings") or [])
    if args.strict:
        blocking += warnings
    out = Path(args.out) if args.out else ROOT / "qa" / args.project / "composition.json"
    write_json(out, report)
    print(f"plan: {plan_path}")
    print(
        f"scenes: {len(report['scenes'])} · blocking: {len(report['blocking'])} "
        f"· warnings: {len(report['warnings'])}"
    )
    for item in report["blocking"][:20]:
        print("  ✘", json.dumps(item, ensure_ascii=False))
    for item in report["warnings"][:10]:
        print("  ⚠", json.dumps(item, ensure_ascii=False))
    print(f"report: {out}")
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
