"""تثبيت أدوات الصوت المحلية — تنزيل واحد، بلا خدمات سحابية.

الأدوات:
* **Piper** — تنفيذ التوليد (22.4MB) + نموذج عربي (63.2MB).
* **whisper.cpp** — تنفيذ التفريغ (8.9MB) + النموذج `ggml-tiny` (77.7MB).

كل شيء يُنزَّل مرة واحدة إلى ``runtime/`` (مستثنى من Git) — ولا يُنزَّل شيء
بلا علم صريح: ``--piper`` / ``--asr`` يختاران ما تريده.

    python tools\\setup_local_tts.py --piper          # التوليد فقط
    python tools\\setup_local_tts.py --asr            # التفريغ فقط
    python tools\\setup_local_tts.py --piper --asr    # كل شيء
    python tools\\setup_local_tts.py --status         # فحص
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"

PIPER_ZIP = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
PIPER_MODEL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx"
PIPER_MODEL_JSON = PIPER_MODEL + ".json"
WHISPER_ZIP = "https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-x64.zip"
WHISPER_MODEL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin"

EXPECTED = {
    "piper_windows_amd64.zip": 22_477_236,
    "ar_JO-kareem-medium.onnx": 63_201_294,
    "ar_JO-kareem-medium.onnx.json": 5_024,
    "whisper-bin-x64.zip": 8_928_640,
    "ggml-tiny.bin": 77_691_713,
}


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↓ {url.rsplit('/', 1)[-1]}")
    req = urllib.request.Request(url, headers={"User-Agent": "rasm-pro-setup"})
    with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)
    return dest


def _verify(path: Path) -> bool:
    expected = EXPECTED.get(path.name)
    if not expected:
        return True
    size = path.stat().st_size
    if size != expected:
        print(f"  ⚠ الحجم غير مطابق: {path.name} = {size} (المتوقع {expected})")
        return False
    return True


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def install_piper() -> int:
    downloads = RUNTIME / "downloads"
    print("· Piper:")
    zip_path = downloads / "piper_windows_amd64.zip"
    if not zip_path.exists() or not _verify(zip_path):
        _download(PIPER_ZIP, zip_path)
    target = RUNTIME / "piper"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)
    exe = target / "piper" / "piper.exe"
    if not exe.exists():
        exe = target / "piper.exe"
    print(f"  ✔ التنفيذ: {exe}")

    models = RUNTIME / "tts-models"
    models.mkdir(parents=True, exist_ok=True)
    for url in (PIPER_MODEL, PIPER_MODEL_JSON):
        name = url.rsplit("/", 1)[-1]
        dest = models / name
        if not dest.exists() or not _verify(dest):
            _download(url, dest)
        print(f"  ✔ النموذج: {dest} ({dest.stat().st_size / 1e6:.1f}MB)")
    return 0


def install_asr() -> int:
    downloads = RUNTIME / "downloads"
    print("· whisper.cpp:")
    zip_path = downloads / "whisper-bin-x64.zip"
    if not zip_path.exists() or not _verify(zip_path):
        _download(WHISPER_ZIP, zip_path)
    target = RUNTIME / "whisper"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)
    exe = target / "Release" / "whisper-cli.exe"
    print(f"  ✔ التنفيذ: {exe}")

    models = target / "models"
    models.mkdir(parents=True, exist_ok=True)
    dest = models / "ggml-tiny.bin"
    if not dest.exists() or not _verify(dest):
        _download(WHISPER_MODEL, dest)
    print(f"  ✔ النموذج: {dest} ({dest.stat().st_size / 1e6:.1f}MB)")
    return 0


def status() -> int:
    sys.path.insert(0, str(ROOT))
    from engine.audio.asr import asr_status
    from engine.audio.tts import piper_status

    tts = piper_status("ar")
    asr = asr_status()
    print("· TTS (Piper):")
    print(f"   التنفيذ: {tts.get('binary') or '—'}")
    print(f"   النموذج: {tts.get('model') or '—'}")
    print(f"   جاهز: {'نعم' if tts.get('available') else 'لا'}")
    print("· ASR (whisper.cpp):")
    print(f"   التنفيذ: {asr.get('binary') or '—'}")
    print(f"   النموذج: {asr.get('model') or '—'}")
    print(f"   جاهز: {'نعم' if asr.get('available') else 'لا'}")
    ok = bool(tts.get("available") and asr.get("available"))
    if ok:
        manifest = {
            "piper": {"binary": tts.get("binary"), "model": tts.get("model")},
            "asr": {"binary": asr.get("binary"), "model": asr.get("model")},
        }
        (RUNTIME / "tools-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="تثبيت أدوات الصوت المحلية")
    ap.add_argument("--piper", action="store_true", help="تثبيت TTS المحلي (Piper)")
    ap.add_argument("--asr", action="store_true", help="تثبيت التفريغ المحلي (whisper.cpp)")
    ap.add_argument("--status", action="store_true", help="فحص الأدوات المثبَّتة")
    args = ap.parse_args()

    if args.status or not (args.piper or args.asr):
        return status()
    if args.piper:
        install_piper()
    if args.asr:
        install_asr()
    print()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
