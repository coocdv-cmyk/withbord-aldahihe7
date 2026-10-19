"""Objective quality checks for generated assets.

No vision-language model is required. The checks are deliberately mechanical:
palette distance, saturation, edge/contrast in the text-safe zone, face count,
alpha coverage, resolution and perceptual hash. They reject obvious failures;
a human still approves the final asset.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .style import all_palette

_CASCADE = None


def _face_cascade():
    global _CASCADE
    if _CASCADE is None:
        try:
            path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            _CASCADE = cv2.CascadeClassifier(str(path))
        except Exception:
            _CASCADE = False
    return _CASCADE


def _lab_palette(style: dict) -> np.ndarray:
    colors = np.array(all_palette(style), np.uint8).reshape(1, -1, 3)
    return cv2.cvtColor(colors, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)


def palette_distance(img: Image.Image, style: dict) -> float:
    arr = np.asarray(img.convert("RGB").resize((256, 256)), np.uint8)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    pal = _lab_palette(style)
    if not len(pal):
        return 0.0
    d = np.linalg.norm(lab[:, None, :] - pal[None, :, :], axis=2).min(axis=1)
    return float(d.mean())


def phash(img: Image.Image) -> str:
    g = np.asarray(img.convert("RGB").convert("L").resize((32, 32), Image.Resampling.LANCZOS), np.float32)
    d = cv2.dct(g)[:8, :8]
    med = float(np.median(d[1:]))
    bits = (d > med).flatten()
    value = 0
    for b in bits:
        value = (value << 1) | int(bool(b))
    return f"{value:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def _zone_px(size: tuple[int, int], zone: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    w, h = size
    x, y, zw, zh = zone
    x0 = max(0, min(w - 1, int(round(x * w))))
    y0 = max(0, min(h - 1, int(round(y * h))))
    x1 = max(x0 + 1, min(w, int(round((x + zw) * w))))
    y1 = max(y0 + 1, min(h, int(round((y + zh) * h))))
    return x0, y0, x1, y1


def text_zone_metrics(img: Image.Image, zone: tuple[float, float, float, float]) -> dict:
    arr = np.asarray(img.convert("RGB"), np.uint8)
    x0, y0, x1, y1 = _zone_px(img.size, zone)
    crop = cv2.cvtColor(arr[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY)
    contrast = float(crop.std())
    edges = cv2.Canny(crop, 45, 135)
    edge = float((edges > 0).mean())
    dark = float((crop < 92).mean())
    busy = float(np.clip(0.55 * (edge / 0.18) + 0.45 * (contrast / 55.0), 0.0, 1.0))
    return {
        "contrast": round(contrast, 2),
        "edge_density": round(edge, 4),
        "dark_ratio": round(dark, 4),
        "busy": round(busy, 4),
    }


def analyze(img: Image.Image, style: dict, spec: dict, *, purpose: str,
            zone: tuple[float, float, float, float] | None = None) -> dict:
    qa = style.get("qa") or {}
    arr = np.asarray(img.convert("RGB"), np.uint8)
    h, w = arr.shape[:2]
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    edges = cv2.Canny(gray, 60, 160)
    edge_density = float((edges > 0).mean())
    saturation = float(hsv[..., 1].mean() / 255.0)
    pdist = palette_distance(img, style)
    alpha_cov = 1.0
    if img.mode in ("RGBA", "LA"):
        a = np.asarray(img.getchannel("A"))
        alpha_cov = float((a > 8).mean())

    z = zone or style.get("text_safe_zone") or (0.18, 0.18, 0.64, 0.55)
    tz = text_zone_metrics(img, tuple(float(v) for v in z))

    faces = 0
    cascade = _face_cascade()
    if cascade:
        scale = min(1.0, 640.0 / max(w, h))
        small = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))))
        found = cascade.detectMultiScale(small, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        faces = int(len(found))

    failures: list[str] = []
    min_res = qa.get("min_resolution") or [768, 512]
    if purpose == "overlay":
        min_res = [256, 256]
    elif purpose == "scrap":
        min_res = [384, 384]
    if w < int(min_res[0]) or h < int(min_res[1]):
        failures.append(f"resolution {w}x{h} < {min_res[0]}x{min_res[1]}")
    if faces > int(qa.get("max_faces", 0)):
        failures.append(f"faces detected: {faces}")
    if pdist > float(qa.get("max_palette_distance", 44.0)):
        failures.append(f"palette distance {pdist:.1f} > {qa.get('max_palette_distance', 44.0)}")
    if saturation > float(qa.get("max_saturation", 0.50)):
        failures.append(f"saturation {saturation:.2f} > {qa.get('max_saturation', 0.50)}")
    if purpose not in ("overlay", "scrap") and tz["busy"] > float(qa.get("max_text_zone_busy", 0.18)):
        failures.append(f"text zone busy {tz['busy']:.2f} > {qa.get('max_text_zone_busy', 0.18)}")
    need_alpha = purpose in ("overlay", "scrap") or bool(spec.get("requires_alpha"))
    if need_alpha and alpha_cov < float(qa.get("min_alpha_coverage", 0.015)):
        failures.append(f"alpha coverage {alpha_cov:.3f} too low")

    score = 100.0
    score -= min(38.0, pdist * 0.62)
    score -= max(0.0, saturation - 0.34) * 90.0
    if purpose not in ("overlay",):
        score -= max(0.0, tz["busy"] - 0.10) * 55.0
    score -= max(0.0, edge_density - 0.12) * 90.0
    score -= faces * 35.0
    if need_alpha and alpha_cov < 0.015:
        score -= 20.0
    score = float(np.clip(score, 0.0, 100.0))

    return {
        "pass": not failures,
        "score": round(score, 1),
        "failures": failures,
        "width": w,
        "height": h,
        "palette_distance": round(pdist, 2),
        "saturation": round(saturation, 3),
        "edge_density": round(edge_density, 4),
        "alpha_coverage": round(alpha_cov, 4),
        "faces": faces,
        "text_zone": tz,
        "phash": phash(img),
    }
