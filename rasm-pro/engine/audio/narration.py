"""استيراد التعليق الصوتي: نسخة داخل المشروع + بصمة + وصف + قياس جهارة.

- الأصل لا يُلمس أبدًا: ننسخ (copy) إلى ``audio/`` بأسم مبني على البصمة، فيصبح
  المرجع ثابتًا حتى لو تغيّر ملف المستخدم لاحقًا.
- لا تكرار: نفس البصمة ⇒ نفس الملف ⇒ لا نسخ جديد.
- المسارات **نسبية للمشروع** (تناسقًا مع عقد المانيفست) فيبقى المشروع قابلًا
  للنقل؛ المسار المطلق للمصدر الخارجي يُحفظ في ``original`` فقط.
- الوصف يُحفظ في ``audio/narration.json`` (كوديك/معدل/قنوات/مدة/عينات/قمم/بصمة)
  مع **تقرير جهارة** مقيس (ITU-R BS.1770-4).
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..core.log import get_logger
from ..core.util import write_json
from .loudness import LoudnessError, measure_loudness
from .probe import AudioError, probe_audio, sha256_file

log = get_logger("audio.narration")

MANIFEST_NAME = "narration.json"
MAX_NORMALIZE_GAIN_DB = 12.0


def audio_dir(project_dir: str | Path) -> Path:
    d = Path(project_dir) / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def narration_path(project_dir: str | Path) -> Path:
    m = load_narration(project_dir)
    if not m:
        return audio_dir(project_dir) / "narration.wav"
    return resolve_narration(project_dir, m)


def resolve_narration(project_dir: str | Path, manifest: dict | None = None) -> Path:
    """Resolve the stored narration file (relative paths are project relative)."""
    m = manifest or load_narration(project_dir) or {}
    stored = str((m.get("stored") or {}).get("path") or m.get("path") or "")
    if not stored:
        return audio_dir(project_dir) / "narration.wav"
    p = Path(stored)
    if p.is_absolute():
        return p
    return (Path(project_dir) / p).resolve()


def import_narration(
    project_dir: str | Path,
    src: str | Path,
    *,
    copy: bool = True,
    deep: bool = True,
    note: str = "",
    origin: dict | None = None,
) -> dict:
    """يستورد تعليقًا صوتيًا لمشروع ويعيد وصفه الكامل مع قياس جهارته.

    ``origin`` يصف **أصلية** الصوت عندما لا يكون ملفًا خارجيًا: مثلًا
    ``{"kind": "generated", "generated_by": "engine.tts", ...}``.  بدونه
    يُعتبر الملف نسخة من أصل خارجي كما كان.
    """
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

    loudness = None
    try:
        loudness = measure_loudness(dst).to_dict()
    except LoudnessError as exc:
        log.warning("تعذّر قياس الجهارة: %s", exc)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if origin:
        source_block = {
            "path": str(src.resolve()),
            "name": src.name,
            "sha256": digest,
            "outside_project": bool(origin.get("outside_project", True)),
            **{k: v for k, v in origin.items() if k != "outside_project"},
        }
    else:
        source_block = {
            "path": str(src.resolve()),
            "name": src.name,
            "sha256": digest,
            "outside_project": True,
        }
    manifest = {
        "version": 2,
        "imported_at": now,
        "note": note,
        "original": source_block,
        "stored": {
            "path": dst.relative_to(Path(project_dir)).as_posix() if copy else str(dst.resolve()),
            "name": dst.name,
            "copied": bool(copy and dst != src),
        },
        **{k: v for k, v in desc.items() if k not in ("path",)},
        "path": dst.relative_to(Path(project_dir)).as_posix() if copy else str(dst.resolve()),
        "loudness": loudness,
        "loudness_measured_at": now if loudness else None,
        "normalization": None,
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
    if not m.get("path"):
        return None
    resolved = resolve_narration(project_dir, m)
    if not resolved.exists():
        return None
    return m


def measure_project_narration(project_dir: str | Path) -> dict | None:
    """(Re)measure the loudness of the stored narration and store the report."""
    m = load_narration(project_dir)
    if not m:
        return None
    path = resolve_narration(project_dir, m)
    try:
        report = measure_loudness(path).to_dict()
    except LoudnessError as exc:
        log.warning("تعذّر قياس الجهارة: %s", exc)
        return None
    m["loudness"] = report
    m["loudness_measured_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(audio_dir(project_dir) / MANIFEST_NAME, m)
    return report


def normalize_narration(
    project_dir: str | Path,
    target_lufs: float,
    *,
    max_gain_db: float = MAX_NORMALIZE_GAIN_DB,
) -> dict:
    """Normalize the **stored copy** to a target loudness, explicitly and logged.

    * The original file is never touched.
    * The gain is bounded: beyond ±``max_gain_db`` the request is refused
      (a silent -30 dB boost would be noise, not normalization).
    * The before/after measurements and the applied gain are written to
      ``audio/narration.json``.
    """
    import subprocess

    from ..render.video import require_ffmpeg
    from .probe import require_ffprobe  # noqa: F401  (explicit discovery)

    m = load_narration(project_dir)
    if not m:
        raise AudioError("لا يوجد تعليق صوتي مستورد في هذا المشروع")
    before = m.get("loudness")
    if not before or not isinstance(before, dict):
        before = measure_project_narration(project_dir)
    if not before:
        raise AudioError("تعذّر قياس الجهارة قبل التطبيع")

    measured = float(before.get("lufs_integrated") or 0.0)
    gain = float(target_lufs) - measured
    if abs(gain) > max_gain_db:
        raise AudioError(
            f"كسب التطبيع {gain:+.2f} dB يتجاوز الحد المسموح (±{max_gain_db:.0f} dB) — "
            "المصدر أبعد عن الهدف؛ أصلح التسجيل بدل ترفع الضجيج."
        )

    src = resolve_narration(project_dir, m)
    exe = require_ffmpeg()
    out = audio_dir(project_dir) / f"narration-norm-{target_lufs:+.0f}lufs{src.suffix.lower() or '.wav'}"
    cmd = [
        exe,
        "-y",
        "-v",
        "error",
        "-i",
        str(src),
        "-af",
        f"volume={gain:.4f}dB",
        "-c:a",
        "pcm_s16le",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AudioError(f"فشل التطبيع: {proc.stderr[-300:]}")
    after = measure_loudness(out).to_dict()
    digest = sha256_file(out)
    # The stored file changed: every top-level descriptor must describe the
    # new bytes, not the pre-normalization source.  Otherwise the production
    # contract compares a fresh SHA against a stale manifest and refuses.
    desc = probe_audio(out, deep=True)
    for key, value in desc.items():
        if key == "path":
            continue
        m[key] = value

    m["normalization"] = {
        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_lufs": float(target_lufs),
        "gain_db": round(gain, 2),
        "before": before,
        "after": after,
        "file": out.relative_to(Path(project_dir)).as_posix(),
        "sha256": digest,
        "source_sha256": sha256_file(src),
    }
    m["loudness"] = after
    m["loudness_measured_at"] = m["normalization"]["applied_at"]
    m["stored"] = {
        "path": out.relative_to(Path(project_dir)).as_posix(),
        "name": out.name,
        "copied": True,
    }
    m["path"] = out.relative_to(Path(project_dir)).as_posix()
    write_json(audio_dir(project_dir) / MANIFEST_NAME, m)
    return m["normalization"]
