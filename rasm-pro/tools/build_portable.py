#!/usr/bin/env python
"""Build the one-folder Windows spike (Stage 2).

Usage:
    python tools/build_portable.py [--pyinstaller PATH] [--out DIR]

The result is a *spike*, not the final installer.  It intentionally excludes
models, runtime binaries, projects, backups and credentials.  The executable
uses ``RASM_HOME`` (or its own directory) for writable data.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# the Windows console is cp1252: the tick marks below would crash the build
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_OUT = ROOT / "build" / "portable"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pyinstaller", default=None, help="Path to pyinstaller.exe (optional)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--name", default="rasm")
    args = ap.parse_args()

    if args.pyinstaller:
        pyinstaller_cmd = [str(Path(args.pyinstaller))]
        extra_env = {}
    else:
        pyinstaller_cmd = [sys.executable, "-m", "PyInstaller"]
        extra_env = {}

    out = Path(args.out).resolve()
    dist = out / "dist"
    work = out / "build"
    spec = out / "spec"
    for d in (dist, work, spec):
        d.mkdir(parents=True, exist_ok=True)

    sep = ";" if os.name == "nt" else ":"
    add_data = [
        (ROOT / "assets", "assets"),
        (ROOT / "config.example.json", "."),
        (ROOT / "engine" / "core" / "schema", "engine/core/schema"),
        (ROOT / "style_packs" / "paper_ink_v1.json", "style_packs"),
    ]
    cmd = [
        *pyinstaller_cmd,
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name",
        args.name,
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
        "--collect-submodules",
        "engine",
    ]
    for src, dst in add_data:
        if src.exists():
            cmd += ["--add-data", f"{src}{sep}{dst}"]
    cmd.append(str(ROOT / "rasm.py"))

    env = os.environ.copy()
    env.update(extra_env)
    print("• " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
    if proc.returncode != 0:
        return proc.returncode

    app = dist / args.name
    # Writable sidecars that are safe to ship: style packs only. Projects,
    # models, runtime binaries, logs, caches and config.json stay local.
    style_src = ROOT / "style_packs" / "paper_ink_v1.json"
    style_dst = app / "style_packs"
    if style_src.exists():
        style_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(style_src, style_dst / style_src.name)
    print(f"✔ one-folder spike: {app}")
    print(f"  executable: {app / (args.name + '.exe')}")
    print("  data root: next to the executable, or set RASM_HOME")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
