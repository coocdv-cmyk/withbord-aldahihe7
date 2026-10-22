"""بناء حزمة التسليم: تطبيق مجمَّد + مثبّت + سجلّ بصمات + أرشيف.

ما يلمسه المستخدم في النهاية: ملف ``rasm-<date>-win64.zip`` يفتحه، يشغّل
``install.ps1``، فيصبح ``rasm.exe`` على جهازه.

ما لا يدخل الحزمة (بالقصد): الموديلات، المشاريع، الاعتمادات، مفاتيح API،
المؤثرات المُولَّدة. الحزمة **أداة**، لا بيانات.

    python tools\\build_installer.py            # بناء + أرشفة
    python tools\\build_installer.py --skip-build   # أرشفة الموجود فقط
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_OUT = ROOT / "build" / "release"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_app(out: Path) -> Path:
    """يبني التطبيق المجمَّد (onedir) عبر أداة الحزمة الموجودة."""
    cmd = [sys.executable, str(HERE / "build_portable.py"), "--out", str(out / "portable")]
    print("• " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    app = out / "portable" / "dist" / "rasm"
    if not (app / "rasm.exe").exists():
        raise SystemExit(f"لم يُنتج البناء: {app / 'rasm.exe'}")
    return app


def stage_release(app: Path, out: Path) -> Path:
    """يجمع مجلد التسليم: التطبيق + المثبّت + الوثائق + السجل."""
    stage = out / "rasm-installer"
    if stage.exists():
        shutil.rmtree(stage)
    payload = stage / "rasm"
    shutil.copytree(app, payload)

    for name in ("install.ps1", "uninstall.ps1"):
        shutil.copy2(ROOT / "installer" / name, stage / name)

    docs = stage / "docs"
    docs.mkdir(exist_ok=True)
    for name in ("21-LOCAL-VOICE-AND-WORD-ALIGNMENT-AR.md", "20-SCRIPT-IN-VIDEO-OUT-AR.md"):
        src = ROOT / "docs" / name
        if src.exists():
            shutil.copy2(src, docs / name)

    readme = stage / "README-AR.md"
    readme.write_text(
        "# راسم — حزمة التسليم\n\n"
        "## التثبيت\n\n"
        "```powershell\n"
        "powershell -ExecutionPolicy Bypass -File install.ps1\n"
        "```\n\n"
        "ثم:\n\n"
        "```powershell\n"
        "rasm --help\n"
        "rasm build my-episode --script script.txt --tts piper --asr\n"
        "```\n\n"
        "## ما تحتاجه على جهازك\n\n"
        "* **ffmpeg** (اختياري للمعاينة) — من `winget install ffmpeg` أو choco.\n"
        "* **أدوات الصوت المحلية** (اختيارية للسرد المحلي والتفريغ):\n"
        "  `python tools\\setup_local_tts.py --piper --asr` — 163MB، تنزيل واحد.\n"
        "* لا حساب، ولا سحابة، ولا اشتراك.\n\n"
        "## الإزالة\n\n"
        "```powershell\n"
        "powershell -ExecutionPolicy Bypass -File uninstall.ps1\n"
        "```\n",
        encoding="utf-8",
    )

    # سجل البصمات: كل ملف في الحزمة
    lines = []
    for path in sorted(stage.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(stage).as_posix()
        lines.append(f"{_sha256(path)}  {rel}")
    (stage / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="ascii")

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": len(lines),
        "bytes": sum(p.stat().st_size for p in stage.rglob("*") if p.is_file()),
        "python": sys.version.split()[0],
    }
    (stage / "BUILD-INFO.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stage


def archive(stage: Path, out: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    zip_path = out / f"rasm-{stamp}-win64.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(stage).as_posix())
    return zip_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--skip-build", action="store_true", help="أرشفة الموجود بلا إعادة بناء")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    app = out / "portable" / "dist" / "rasm"
    if not args.skip_build:
        app = build_app(out)
    elif not app.exists():
        print("✘ لا يوجد بناء سابق (استعمل --skip-build مع build موجود فقط)")
        return 2

    stage = stage_release(app, out)
    zip_path = archive(stage, out)
    size = zip_path.stat().st_size
    print(f"✔ الحزمة: {zip_path}")
    print(f"  الحجم: {size / 1e6:.1f}MB · الملفات: {sum(1 for _ in stage.rglob('*') if _.is_file())}")
    print(f"  البصمة: {_sha256(zip_path)}")
    print(f"  التثبيت: powershell -ExecutionPolicy Bypass -File install.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
