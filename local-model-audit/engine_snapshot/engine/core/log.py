"""تسجيل موحّد للعمليات."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .paths import LOGS

_configured = False


def get_logger(name: str = "rasm") -> logging.Logger:
    global _configured
    if not _configured:
        root = logging.getLogger("rasm")
        root.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(name)s  %(message)s", "%H:%M:%S")

        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        root.addHandler(sh)

        fh = logging.FileHandler(Path(LOGS) / "engine.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        _configured = True
    return logging.getLogger(f"rasm.{name}" if name != "rasm" else "rasm")
