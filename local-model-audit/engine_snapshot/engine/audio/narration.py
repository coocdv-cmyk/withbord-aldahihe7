"""استيراد التعليق الصوتي: نسخة داخل المشروع + بصمة + وصف كامل (بلا تعديل الأصل).

- الأصل لا يُلمس أبدًا: ننسخ (copy) إلى ``audio/`` بأسم مبني على البصمة، فيصبح
  المرجع ثابتًا حتى لو تغيّر ملف المستخدم لاحقًا.
- لا تكرار: نفس البصمة ⇒ نفس الملف ⇒ لا نسخ جديد.
- الوصف يُحفظ في ``audio/narration.json`` (كوديك/معدل/قنوات/مدة/عينات/قمم/بصمة).
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..core.log import get_logger
from ..core.util import write_json
from .probe import AudioError, probe_audio, sha256_file

log = get_logger("audio.narration")

MANIFEST_NAME = "narration.json"


def audio_dir(project_dir: str | Path) -> Path:
    d = Path(project_dir) / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def narration_path(project_dir: str | Path) -> Path:
    m = load_narration(project_dir)
    if not m:
        return audio_dir(project_dir) / "narration.wav"
    p = Path((m.get("stored") or {}).get("path") or "")
    return p


def import_narration(
    project_dir: str | Path,
    src: str | Path,
    *,
    copy: bool = True,
    deep: bool = True,
    note: str = "",
) -> dict:
    """يستورد تعليقًا صوتيًا لمشروع ويعيد وصفه الكامل."""
    src = Path(src)
    if not src.exists():
        raise AudioError(f"ملف التعليق غير موجود: {src}")

    digest = sha256_file(src)
    adir = audio_dir(project_dir)
    ext = src.suffix.lower() or ".wav"
    dst = adir / f"narration-{digest[:10]}{ext}"

    if copy:
        if not dst.exists():
            shutil.copy2(src, dst)  # الأصل لا يُعدَّل — نسخة فقط
            log.info("نُسخ التعليق: %s → %s", src.name, dst.name)
    else:
        dst = src  # مرجع مباشر (لا نسخ) — للملفات الكبيرة جدًا

    desc = probe_audio(dst, deep=deep)
    if desc["sha256"] != digest and copy:
        # نسخة مشوّهة؟ (يستحيل عمليًا) — نرفض بدل الصمت
        raise AudioError("بصمة النسخة لا تطابق الأصل — أعد النسخ")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {
        "version": 1,
        "imported_at": now,
        "note": note,
        "original": {"path": str(src.resolve()), "name": src.name, "sha256": digest},
        "stored": {
            "path": str(dst.resolve()),
            "name": dst.name,
            "copied": bool(copy and dst != src),
        },
        **{k: v for k, v in desc.items() if k not in ("path",)},
        "path": str(dst.resolve()),
    }
    write_json(adir / MANIFEST_NAME, manifest)
    return manifest


def load_narration(project_dir: str | Path) -> dict | None:
    """وصف التعليق الصوتي المستورد (أو None)."""
    import json

    p = audio_dir(project_dir) / MANIFEST_NAME
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not m.get("path") or not Path(m["path"]).exists():
        return None
    return m
