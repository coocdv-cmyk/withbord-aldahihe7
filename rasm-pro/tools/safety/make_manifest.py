"""بناء بيان بصمات SHA256 لمجلد أو أكثر — إضافة أمان فقط ولا تعدل أي شيء.

الاستخدام:
    python make_manifest.py <out.csv> <root1> [root2 ...]

تُكتب المسارات نسبةً إلى المجلد الأب لكل جذر (لذا مرّر مجلدات شقيقة مثل
...\\rasm-pro\\projects و ...\\rasm-pro\\assets لتحصل على مسارات راسم-برو\\...).
"""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest().upper()


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: make_manifest.py <out.csv> <root1> [root2 ...]")
        return 2
    out = Path(sys.argv[1])
    roots = [Path(p) for p in sys.argv[2:]]
    rows: list[tuple[str, int, str]] = []
    count = 0
    total = 0
    for root in roots:
        if not root.exists():
            print(f"missing: {root}")
            return 3
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root.parent)
            digest = sha256_file(p)
            size = p.stat().st_size
            rows.append((str(rel).replace("\\", "/"), size, digest))
            count += 1
            total += size
            if count % 5000 == 0:
                print(f"...{count} files")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["path", "size_bytes", "sha256"])
        w.writerows(rows)
    print(f"OK files={count} bytes={total} csv={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
