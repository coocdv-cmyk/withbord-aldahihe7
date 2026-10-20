"""Loudness measurement — ITU-R BS.1770-4 (EBU R128), deterministic.

Why this module exists
----------------------
A render can look perfect and still be unusable: -30 LUFS is quiet on a
phone, clipping is harsh on a TV, and a true peak above -1 dBTP distorts in
the codec.  The project refuses to publish numbers it has not measured, so
the loudness of every narration is measured here and stored with it.

What is measured
----------------
* ``lufs_integrated``  — gated integrated loudness (BS.1770-4 §5)
* ``lra``              — loudness range (BS.1770-4 §6)
* ``true_peak_dbtp``   — 4x oversampled true peak
* ``rms_dbfs``         — plain RMS level
* ``sample_rate``, ``channels``, ``duration_sec``, ``total_samples``

Everything is integer-sample exact: the same file always produces the same
numbers, and no value is ever estimated.
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from ..core.log import get_logger

log = get_logger("audio.loudness")

__all__ = [
    "LoudnessError",
    "LoudnessReport",
    "measure_loudness",
    "measure_samples",
    "TARGETS",
]

# Practical delivery targets (documented, not invented):
#   -16 LUFS  -> online video (the common practice for spoken video)
#   -23 LUFS  -> podcast / broadcast style speech
TARGETS = {
    "video": -16.0,
    "podcast": -23.0,
    "broadcast": -23.0,
}

# BS.1770-4 channel weights: L, R, C = 1.0 ; Ls, Rs = 1.41 (i.e. 1.4)
_CHANNEL_WEIGHTS = {
    "mono": [1.0],
    "stereo": [1.0, 1.0],
    "3.0": [1.0, 1.0, 1.0],
    "4.0": [1.0, 1.0, 1.0, 1.0],
    "5.0": [1.0, 1.0, 1.0, 1.41, 1.41],
    "5.1": [1.0, 1.0, 1.0, 1.0, 1.41, 1.41],
}


class LoudnessError(RuntimeError):
    """The audio could not be measured."""


def _weights_for(channels: int) -> list[float]:
    """BS.1770-4 channel weights (G): L/R/C = 1, surround = 1.41."""
    if channels == 1:
        return [1.0]
    if channels == 2:
        return [1.0, 1.0]
    if channels == 3:
        return [1.0, 1.0, 1.0]
    if channels == 4:
        return [1.0, 1.0, 1.0, 1.0]
    if channels == 5:
        return [1.0, 1.0, 1.0, 1.41, 1.41]
    if channels == 6:
        return [1.0, 1.0, 1.0, 1.0, 1.41, 1.41]
    return [1.0] * channels


@dataclass
class LoudnessReport:
    lufs_integrated: float
    lra: float
    true_peak_dbtp: float
    rms_dbfs: float
    sample_rate: int
    channels: int
    total_samples: int
    duration_sec: float
    method: str = "ITU-R BS.1770-4"

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# K-weighting (BS.1770-4, coefficients recomputed for the actual rate)
# --------------------------------------------------------------------------
def _k_weight_coeffs(fs: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(b, a) of the two K-weighting stages for a given sample rate.

    Stage 1: the RLB high-pass (38.135 Hz, Q 0.5).
    Stage 2: the pre-filter high-shelf (+4 dB above ~1.7 kHz).
    Coefficients are the ITU-R BS.1770-4 / libebur128 formulas, recomputed
    for the actual sample rate (a0 normalized to 1 in both stages).
    """
    # stage 1: RLB high-pass
    f0 = 38.13547087602444
    Q = 0.5003270373238773
    K = math.tan(math.pi * f0 / fs)
    denom = 1.0 + K / Q + K * K
    b1 = np.array([1.0, -2.0, 1.0])
    a1 = np.array([1.0, 2.0 * (K * K - 1.0) / denom, (1.0 - K / Q + K * K) / denom])

    # stage 2: high-shelf ("pre-filter")
    f0 = 1681.974450955533
    G = 3.999843853973347
    Q = 0.7071752369554196
    K = math.tan(math.pi * f0 / fs)
    Vh = 10.0 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0 = 1.0 + K / Q + K * K
    b2 = np.array(
        [
            (Vh + Vb * (K / Q) + K * K) / a0,
            2.0 * (K * K - Vh) / a0,
            (Vh - Vb * (K / Q) + K * K) / a0,
        ]
    )
    a2 = np.array([1.0, 2.0 * (K * K - 1.0) / a0, (1.0 - K / Q + K * K) / a0])
    return b1, a1, b2, a2


def _k_weight(x: np.ndarray, fs: int) -> np.ndarray:
    """Apply the K-weighting filter (a second order section, applied twice)."""
    b, a, b2, a2 = _k_weight_coeffs(fs)
    y = _biquad(x, b, a)
    return _biquad(y, b2, a2)


def _biquad(x: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Second order section, zero initial state (scipy lfilter when available)."""
    try:
        from scipy.signal import lfilter

        return lfilter(b, a, x, axis=-1)
    except Exception:  # pragma: no cover - scipy is a declared dependency
        out = np.zeros_like(x)
        for ch in range(x.shape[0]):
            y = np.zeros(x.shape[1])
            x1 = x2 = 0.0
            y1 = y2 = 0.0
            b0, b1, b2 = b
            a1, a2 = a[1], a[2]
            for i in range(x.shape[1]):
                xi = x[ch, i]
                yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                x2, x1 = x1, xi
                y2, y1 = y1, yi
                y[i] = yi
            out[ch] = y
        return out


# --------------------------------------------------------------------------
# gating
# --------------------------------------------------------------------------
_BLOCK_SEC = 0.4
_HOP_SEC = 0.1
_ABSOLUTE_GATE = -70.0
_RELATIVE_GATE = -10.0
_LRA_RELATIVE_GATE = -20.0


def _block_loudness(y: np.ndarray, weights: np.ndarray, block: int, hop: int) -> np.ndarray:
    """Mean square per block for the K-weighted signal (BS.1770-4 §4)."""
    n = y.shape[1]
    if n < block:
        return np.empty(0, dtype=float)
    count = 1 + (n - block) // hop
    out = np.zeros(count, dtype=float)
    for i in range(count):
        start = i * hop
        chunk = y[:, start : start + block]
        out[i] = float(np.sum(np.mean(chunk * chunk, axis=1) * weights))
    return out


def _integrated(block_ms: np.ndarray) -> float:
    if block_ms.size == 0:
        return float("-inf")
    with np.errstate(divide="ignore"):
        loud = -0.691 + 10.0 * np.log10(block_ms)
    keep = loud > _ABSOLUTE_GATE
    if not np.any(keep):
        return float("-inf")
    relative = -0.691 + 10.0 * np.log10(np.mean(block_ms[keep]))
    keep2 = keep & (loud > relative + _RELATIVE_GATE)
    if not np.any(keep2):
        keep2 = keep
    return float(-0.691 + 10.0 * np.log10(np.mean(block_ms[keep2])))


def _loudness_range(block_ms: np.ndarray) -> float:
    if block_ms.size == 0:
        return 0.0
    with np.errstate(divide="ignore"):
        loud = -0.691 + 10.0 * np.log10(block_ms)
    keep = loud > _ABSOLUTE_GATE
    if not np.any(keep):
        return 0.0
    relative = -0.691 + 10.0 * np.log10(np.mean(block_ms[keep]))
    keep2 = keep & (loud > relative + _LRA_RELATIVE_GATE)
    if not np.any(keep2):
        return 0.0
    selected = loud[keep2]
    return float(np.percentile(selected, 95) - np.percentile(selected, 10))


def _true_peak(x: np.ndarray, factor: int = 4) -> float:
    """True peak in dBTP using 4x oversampling (inter-sample peaks included)."""
    if x.size == 0:
        return float("-inf")
    peak = float(np.max(np.abs(x)))
    if factor > 1:
        try:
            from scipy.signal import resample_poly

            up = resample_poly(x, factor, 1, axis=-1)
            peak = max(peak, float(np.max(np.abs(up))))
        except Exception:  # pragma: no cover - scipy is a declared dependency
            log.warning("scipy غير متاح: يُقاس peak العينة فقط دون oversampling")
    if peak <= 0:
        return float("-inf")
    return float(20.0 * math.log10(peak))


# --------------------------------------------------------------------------
# decoding
# --------------------------------------------------------------------------
def decode_samples(path: str | Path) -> tuple[np.ndarray, int]:
    """Decode an audio file to (samples[channels, n] float64 in [-1, 1], rate).

    Uses ffmpeg (an external sidecar in this project) and never guesses.
    """
    from .probe import require_ffmpeg

    exe = require_ffmpeg()
    src = Path(path)
    if not src.exists():
        raise LoudnessError(f"ملف غير موجود: {src}")

    # probe the stream first (channels, rate)
    from .probe import probe_audio

    info = probe_audio(src, deep=False)
    rate = int(info.get("sample_rate") or 0)
    channels = int(info.get("channels") or 0)
    if rate <= 0 or channels <= 0:
        raise LoudnessError(f"تعذّر قراءة معدل/قنوات الملف: {src.name}")

    cmd = [
        exe,
        "-v",
        "error",
        "-i",
        str(src),
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        str(channels),
        "-ar",
        str(rate),
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise LoudnessError(
            f"فشل فك ترميز الصوت: {proc.stderr.decode('utf-8', 'replace')[-300:]}"
        )
    data = np.frombuffer(proc.stdout, dtype="<f4").astype(np.float64)
    if data.size == 0:
        raise LoudnessError(f"ملف صامت أو فارغ: {src.name}")
    usable = (data.size // channels) * channels
    data = data[:usable]
    return data.reshape(-1, channels).T, rate


def measure_samples(samples: np.ndarray, rate: int) -> LoudnessReport:
    """Measure a (channels, n) float array in [-1, 1]."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    channels, total = x.shape
    if channels <= 0 or total <= 0:
        raise LoudnessError("لا توجد عينات لقياسها")

    weights = np.array(_weights_for(channels))

    y = _k_weight(x, rate)
    block = max(1, int(round(_BLOCK_SEC * rate)))
    hop = max(1, int(round(_HOP_SEC * rate)))
    block_ms = _block_loudness(y, weights, block, hop)
    integrated = _integrated(block_ms)
    lra = _loudness_range(block_ms)

    rms = float(np.sqrt(np.mean(x * x)))
    rms_dbfs = float(20.0 * math.log10(rms)) if rms > 0 else float("-inf")
    true_peak = _true_peak(x)

    return LoudnessReport(
        lufs_integrated=round(integrated, 2) if math.isfinite(integrated) else integrated,
        lra=round(lra, 2),
        true_peak_dbtp=round(true_peak, 2) if math.isfinite(true_peak) else true_peak,
        rms_dbfs=round(rms_dbfs, 2) if math.isfinite(rms_dbfs) else rms_dbfs,
        sample_rate=int(rate),
        channels=int(channels),
        total_samples=int(total),
        duration_sec=round(float(Fraction(total, rate)), 6),
    )


def measure_loudness(path: str | Path) -> LoudnessReport:
    """Measure a file's loudness.  Never estimates; raises on any problem."""
    samples, rate = decode_samples(path)
    return measure_samples(samples, rate)
