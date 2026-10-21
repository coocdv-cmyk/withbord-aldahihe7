"""Measure the SFX library and write the calibration table.

Every number in ``assets/sfx/calibration.json`` is produced by this script, so
the table can be regenerated and audited at any time:

    python tools/measure_sfx.py            # rewrite the table
    python tools/measure_sfx.py --check    # verify the committed table is current

What is measured
----------------
* ITU-R BS.1770-4: integrated LUFS, true peak, RMS (the Stage 4 meter)
* spectral centroid (Hz) and spectral flatness — the *character* of the
  recording, used to prove that two files are not the same sound twice
* duration, sample rate, channels

The calibration gain stored for each type is the gain that brings the raw
recording to the library target level, so the mix stops depending on
hand-picked constants.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.audio.loudness import measure_loudness  # noqa: E402

SFX_DIR = ROOT / "assets" / "sfx"
TABLE = SFX_DIR / "calibration.json"

# The library target: every type is calibrated to the same loudness, so a
# preset means "this much louder than the rest", not "whatever the file was".
TARGET_LUFS = -30.0
TARGET_TOLERANCE_LU = 0.5

# The role of every recording in the mix.  A file without a role is not kept.
#
# Evaluated and rejected on 2026-10-21: "Pencil scratchings" (PD-Sounds 513,
# gypsygirl) measured a 68.7 Hz spectral centroid against 73.7 Hz for the ink
# pen - acoustically the same family of sound, so it duplicated a role that
# already existed.  It was dropped instead of being downloaded into the
# library; the "quick decorative strokes" role is served by the ink pen
# played back faster (a varispeed type, no new payload).
ROLES = {
    "pen_ink.wav": "handwriting texture (ink pen on paper) - the main writing layer",
    "pen_felt.wav": "light writing layer (felt pen) - soft strokes",
    "page_turn.wav": "paper movement - card placement and scene transition",
}


def spectral_profile(samples: np.ndarray, rate: int) -> dict:
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 2:
        x = x.mean(axis=0)
    if x.size < 1024:
        return {"centroid_hz": 0.0, "flatness": 0.0}
    spectrum = np.abs(np.fft.rfft(x[: min(x.size, rate * 20)])) ** 2
    freqs = np.fft.rfftfreq(min(x.size, rate * 20), 1.0 / rate)
    total = float(np.sum(spectrum))
    if total <= 0:
        return {"centroid_hz": 0.0, "flatness": 0.0}
    centroid = float(np.sum(freqs * spectrum) / total)
    log_spec = np.log(spectrum + 1e-12)
    geo = float(np.exp(np.mean(log_spec)))
    arith = float(np.mean(spectrum))
    flatness = geo / arith if arith > 0 else 0.0
    return {"centroid_hz": round(centroid, 1), "flatness": round(flatness, 6)}


def measure_file(path: Path) -> dict:
    from engine.audio.loudness import decode_samples

    report = measure_loudness(path)
    samples, rate = decode_samples(path)
    profile = spectral_profile(samples, rate)
    return {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "lufs_integrated": report.lufs_integrated,
        "lra": report.lra,
        "true_peak_dbtp": report.true_peak_dbtp,
        "rms_dbfs": report.rms_dbfs,
        "duration_sec": report.duration_sec,
        "sample_rate": report.sample_rate,
        "channels": report.channels,
        **profile,
    }


def build_table() -> dict:
    files = {}
    for name in sorted(ROLES):
        path = SFX_DIR / name
        if not path.exists():
            raise SystemExit(f"missing recording with a declared role: {path}")
        files[name] = measure_file(path)
        files[name]["role"] = ROLES[name]

    # distinctness: two recordings of the same sound would be a duplicate
    names = list(files)
    duplicates = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            ca = files[a]["centroid_hz"]
            cb = files[b]["centroid_hz"]
            if ca and cb and abs(ca - cb) < 120 and abs(files[a]["lufs_integrated"] - files[b]["lufs_integrated"]) < 3:
                duplicates.append((a, b))
    if duplicates:
        raise SystemExit(f"two recordings are not distinct enough to keep both: {duplicates}")

    types = {}
    for name, data in files.items():
        gain = round(TARGET_LUFS - float(data["lufs_integrated"]), 2)
        types[name] = {
            "role": data["role"],
            "lufs_raw": data["lufs_integrated"],
            "true_peak_dbtp": data["true_peak_dbtp"],
            "rms_dbfs": data["rms_dbfs"],
            "centroid_hz": data["centroid_hz"],
            "flatness": data["flatness"],
            "duration_sec": data["duration_sec"],
            "sample_rate": data["sample_rate"],
            "channels": data["channels"],
            "sha256": data["sha256"],
            "calibration_gain_db": gain,
        }
    return {
        "version": 1,
        "measured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "method": "ITU-R BS.1770-4 (engine.audio.loudness) + FFT spectral centroid/flatness",
        "target_lufs": TARGET_LUFS,
        "target_tolerance_lu": TARGET_TOLERANCE_LU,
        "recordings": types,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="measure the SFX library")
    ap.add_argument("--check", action="store_true", help="verify the committed table is current")
    args = ap.parse_args()

    table = build_table()
    if args.check:
        if not TABLE.exists():
            print("calibration.json missing")
            return 2
        committed = json.loads(TABLE.read_text(encoding="utf-8"))
        same = all(
            committed.get("recordings", {}).get(name, {}).get("sha256") == entry["sha256"]
            and committed.get("recordings", {}).get(name, {}).get("calibration_gain_db")
            == entry["calibration_gain_db"]
            for name, entry in table["recordings"].items()
        )
        print("calibration table is current" if same else "calibration table is OUT OF DATE")
        return 0 if same else 2

    TABLE.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"✔ {TABLE}")
    for name, entry in table["recordings"].items():
        print(
            f"  {name:<24} {entry['lufs_raw']:7.2f} LUFS · peak {entry['true_peak_dbtp']:6.2f} dBTP · "
            f"centroid {entry['centroid_hz']:7.1f} Hz · gain {entry['calibration_gain_db']:+6.2f} dB · {entry['role']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
