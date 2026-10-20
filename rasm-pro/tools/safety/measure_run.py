"""قياس تشغيل: زمن الجدار + أدنى ذاكرة حرة للجهاز أثناء تشغيل أمر — لا يعدل أي شيء.

الاستخدام:
    python measure_run.py <out.json> <log.txt> <cmd> [args...]

يشغّل <cmd> ويراقب الذاكرة الحرة كل 0.5 ثانية، ثم يحفظ النتيجة في out.json
ويطبعها. هذا يسمح بقياس أثر Python و ffmpeg معًا على الجهاز.
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import threading
import time
from pathlib import Path


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def memory() -> tuple[int, int]:
    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(st)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        raise OSError("GlobalMemoryStatusEx failed")
    return st.ullTotalPhys, st.ullAvailPhys


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: measure_run.py <out.json> <log.txt> <cmd> [args...]")
        return 2
    out = Path(sys.argv[1])
    log = Path(sys.argv[2])
    cmd = sys.argv[3:]

    total, _ = memory()
    stop = threading.Event()
    samples: list[float] = []

    def sample() -> None:
        while not stop.wait(0.5):
            _, avail = memory()
            samples.append(avail)

    t = threading.Thread(target=sample, daemon=True)
    t.start()
    t0 = time.perf_counter()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8", errors="replace") as lf:
        rc = subprocess.call(cmd, stdout=lf, stderr=subprocess.STDOUT)
    elapsed = time.perf_counter() - t0
    stop.set()
    t.join(timeout=2)
    _, avail_end = memory()
    result = {
        "command": cmd,
        "exit_code": rc,
        "elapsed_s": round(elapsed, 2),
        "min_avail_phys_gb": round(min(samples) / (1024**3), 3) if samples else None,
        "avail_at_end_gb": round(avail_end / (1024**3), 3),
        "total_phys_gb": round(total / (1024**3), 2),
        "samples": len(samples),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
