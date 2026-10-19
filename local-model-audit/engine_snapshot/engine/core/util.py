"""أدوات عامة: JSON، بصمات، معرّفات، تنظيف نصوص.""" 
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any, indent: int = 2) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    return p


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def slugify(text: str, max_len: int = 48) -> str:
    """اسم ملف آمن (يحافظ على العربي)."""
    text = unicodedata.normalize("NFKC", text).strip()
    text = re.sub(r"[^\w\u0600-\u06FF\- ]+", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text)
    return text[:max_len].strip("-") or "item"


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&quot;", '"').replace("&#039;", "'").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
