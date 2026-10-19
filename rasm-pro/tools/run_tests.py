"""مشغّل اختبارات مصغّر (بلا pytest): يكتشف tests/test_*.py وينفّذ دوال test_*."""
from __future__ import annotations

import importlib.util
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    files = sorted((ROOT / "tests").glob("test_*.py"))
    if only:
        files = [f for f in files if only in f.stem]
    if not files:
        print("لا اختبارات.")
        return 1

    total = passed = 0
    failures: list[tuple[str, str]] = []
    t0 = time.time()
    for f in files:
        try:
            mod = load_module(f)
        except Exception:
            failures.append((f.stem, traceback.format_exc()))
            continue
        names = [n for n in dir(mod) if n.startswith("test_") and callable(getattr(mod, n))]
        for n in names:
            total += 1
            try:
                getattr(mod, n)()
                passed += 1
                print(f"  ✔ {f.stem}::{n}")
            except Exception:
                failures.append((f"{f.stem}::{n}", traceback.format_exc()))
                print(f"  ✘ {f.stem}::{n}")

    print(f"\n{passed}/{total} اختبار ناجح · {time.time() - t0:.2f}ث · ملفات: {len(files)}")
    for name, tb in failures:
        print(f"\n===== فشل: {name} =====\n{tb}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
