"""تمرين استعادة حقيقي (G7): هل يمكن العودة من الحزمة فعلًا؟

المرحلة الأولى أخفت أن ``git bundle verify`` يثبت **سلامة** الحزمة، لا
**قابلية الاستعادة**.  هذا التمرين يفعل الاستعادة نفسها:

1. ينسخ الحزمة إلى مجلد مؤقت.
2. ``git clone`` منها (بلا شبكة) ⇒ يجب أن تأتي كل الوسوم والفروع.
3. يبني بيئة افتراضية جديدة من ``requirements.txt`` (بلاImpact على بيئة العمل).
4. يشغّل الاختبارات كاملة.
5. يرندر 5 ثوانٍ من مشروع حقيقي في النسخة المستعادة.
6. يقيس ما استغرقه كل خطوة ويكتب تقريرًا.

الاستعمال::

    .venv\\Scripts\\python.exe tools\\restore_drill.py --bundle backups\\stage0-20261020\\code\\rasm-pro-code.bundle
    .venv\\Scripts\\python.exe tools\\restore_drill.py --bundle ... --skip-venv   # faster
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def _run(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int = 1800,
    env: dict | None = None,
) -> tuple[int, str]:
    import os

    full_env = {**os.environ, **(env or {})}
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=full_env,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(description="restore drill: can we come back from the bundle?")
    ap.add_argument("--bundle", required=True, help="path to the .bundle file")
    ap.add_argument("--workdir", default=None, help="where to restore (a temp dir by default)")
    ap.add_argument("--skip-venv", action="store_true", help="do not build a fresh venv (faster)")
    ap.add_argument("--project", default="stage6-arabic-sample", help="project to render from the restore")
    ap.add_argument("--seconds", type=float, default=5.0)
    args = ap.parse_args()

    bundle = Path(args.bundle).resolve()
    if not bundle.exists():
        print(f"bundle not found: {bundle}", file=sys.stderr)
        return 2
    work = Path(args.workdir).resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="rasm_restore_"))
    work.mkdir(parents=True, exist_ok=True)
    report: dict = {"bundle": str(bundle), "workdir": str(work), "steps": {}}

    started = time.time()
    # the LFS objects are NOT inside a bundle: the checkout must skip the
    # smudge (the pointer files are enough to clone), and the content is
    # fetched afterwards if a remote is reachable.
    code, out = _run(
        ["git", "clone", "--no-hardlinks", str(bundle), "clone"],
        cwd=work,
        env={"GIT_LFS_SKIP_SMUDGE": "1"},
    )
    report["steps"]["clone"] = {"ok": code == 0, "seconds": round(time.time() - started, 1), "tail": out[-400:]}
    if code != 0:
        print("✘ the clone failed — the bundle cannot be restored")
        _write_report(work, report)
        return 1
    clone = work / "clone"

    started = time.time()
    code, out = _run(["git", "lfs", "pull"], cwd=clone, timeout=900)
    report["steps"]["lfs"] = {
        "ok": code == 0,
        "seconds": round(time.time() - started, 1),
        "note": "the bundle carries the pointers; the objects come from the remote",
        "tail": out[-200:],
    }
    # the LFS objects are not inside the bundle; their absence is a real
    # limitation but it does not block the restore of code + tests + render
    report["steps"]["lfs"]["blocking"] = False

    started = time.time()
    code, out = _run(["git", "tag", "--list"], cwd=clone)
    tags = [t for t in out.split() if t.strip()]
    report["steps"]["tags"] = {"ok": code == 0, "count": len(tags), "tags": tags[-12:]}
    report["steps"]["clone_seconds"] = round(time.time() - started, 1)

    venv = clone / ".restore-venv"
    if not args.skip_venv:
        started = time.time()
        code, out = _run([sys.executable, "-m", "venv", str(venv)], cwd=clone, timeout=900)
        if code == 0:
            python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            code, out = _run([str(python), "-m", "pip", "install", "-q", "-r", "rasm-pro/requirements.txt", "pytest"], cwd=clone, timeout=1800)
        report["steps"]["venv"] = {"ok": code == 0, "seconds": round(time.time() - started, 1), "tail": out[-300:]}
    else:
        python = Path(sys.executable)
        report["steps"]["venv"] = {"ok": True, "skipped": True}

    started = time.time()
    code, out = _run([str(python), "-m", "pytest", "-q", "tests"], cwd=clone / "rasm-pro", timeout=3600)
    report["steps"]["tests"] = {"ok": code == 0, "seconds": round(time.time() - started, 1), "tail": out[-400:]}

    started = time.time()
    render_cmd = [
        str(python), "rasm.py", "render", args.project,
        "--out", str(clone / "rasm-pro" / "restore-render.mp4"), "--max-seconds", str(args.seconds),
    ]
    code, out = _run(render_cmd, cwd=clone / "rasm-pro", timeout=1800)
    report["steps"]["render"] = {"ok": code == 0, "seconds": round(time.time() - started, 1), "tail": out[-400:]}

    report["ok"] = all(step.get("ok") for step in report["steps"].values() if isinstance(step, dict))
    report["total_seconds"] = round(time.time() - started, 1)
    _write_report(work, report)
    print(json.dumps(report, ensure_ascii=False, indent=2)[:2000])
    print(f"\nreport: {work / 'restore-drill.json'}")
    return 0 if report["ok"] else 1


def _write_report(work: Path, report: dict) -> None:
    (work / "restore-drill.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
