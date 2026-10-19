"""تنزيل موديل GGUF مع استكمال تلقائي — من HuggingFace."""
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def download(url: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    pos = out.stat().st_size if out.exists() else 0
    headers = {"User-Agent": "rasm-pro/0.1"}
    if pos:
        headers["Range"] = f"bytes={pos}-"
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        if r.status_code == 416:  # اكتمل مسبقًا
            print("مكتمل مسبقًا:", out)
            return out
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0)) + pos
        mode = "ab" if pos else "wb"
        done = pos
        last = time.time()
        with open(out, mode) as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if time.time() - last > 10:
                    last = time.time()
                    pct = (done / total * 100) if total else 0
                    print(f"  {done/1e6:.0f}MB / {total/1e6:.0f}MB ({pct:.0f}%)", flush=True)
    print("تم:", out, f"{out.stat().st_size/1e9:.2f}GB")
    return out


if __name__ == "__main__":
    download(sys.argv[1], Path(sys.argv[2]))
