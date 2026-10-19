"""Deterministic paper, card, scrap and overlay generators (no model needed).

Everything here is seeded and reproducible. The same seed and style produce
the same pixels on every run.
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .style import hex_rgb, palette_colors


# ---------------------------------------------------------------------------
# small deterministic helpers
# ---------------------------------------------------------------------------

def _fractal(w: int, h: int, rng: np.random.Generator, *, scale: int = 8, octaves: int = 5) -> np.ndarray:
    out = np.zeros((h, w), np.float32)
    amp = 1.0
    total = 0.0
    for o in range(octaves):
        sw = max(2, w // (scale * (2 ** o)))
        sh = max(2, h // (scale * (2 ** o)))
        small = rng.random((sh, sw), dtype=np.float32)
        big = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
        out += big * amp
        total += amp
        amp *= 0.55
    out /= max(total, 1e-6)
    out -= float(out.min())
    out /= float(out.max()) + 1e-6
    return out


def _fibers(w: int, h: int, rng: np.random.Generator, *, density: float = 0.22) -> np.ndarray:
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    n = max(40, int(w * h * density / 4000.0))
    for _ in range(n):
        x = float(rng.uniform(0, w))
        y = float(rng.uniform(0, h))
        ln = float(rng.uniform(6, min(90, max(12, w * 0.04))))
        ang = float(rng.uniform(-0.18, 0.18))
        x2 = x + ln * math.cos(ang)
        y2 = y + ln * math.sin(ang)
        v = int(rng.uniform(18, 62))
        d.line([(x, y), (x2, y2)], fill=v, width=1)
    arr = np.asarray(im, np.float32) / 255.0
    return cv2.GaussianBlur(arr, (0, 0), 0.55)


def _paper_base(w: int, h: int, rng: np.random.Generator, base: str, *,
                fibers: float = 0.55, mottle: float = 0.7) -> np.ndarray:
    color = np.array(hex_rgb(base), np.float32)
    n = _fractal(w, h, rng, scale=9, octaves=5)
    f = _fibers(w, h, rng)
    shade = (n - 0.5) * 20.0 * mottle + (f - 0.5) * 12.0 * fibers
    arr = color[None, None, :] + shade[..., None]
    return np.clip(arr, 0, 255)


def _stains(arr: np.ndarray, rng: np.random.Generator, *, count: int = 8,
            strength: float = 0.16, color: tuple[int, int, int] = (122, 86, 48)) -> np.ndarray:
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    alpha = np.zeros((h, w), np.float32)
    for _ in range(max(0, count)):
        cx = float(rng.uniform(0, w))
        cy = float(rng.uniform(0, h))
        r = float(rng.uniform(min(w, h) * 0.035, min(w, h) * 0.16))
        sx = r * float(rng.uniform(0.7, 1.7))
        sy = r * float(rng.uniform(0.7, 1.7))
        m = np.exp(-(((xx - cx) ** 2) / (2 * sx * sx) + ((yy - cy) ** 2) / (2 * sy * sy)))
        a = float(rng.uniform(0.22, 0.8)) * strength
        alpha = np.maximum(alpha, m * a)
        # a thin darker rim makes the stain read as liquid, not a soft blob
        d = np.sqrt(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2)
        ring = np.exp(-((d - 1.05) ** 2) / (2 * 0.055 ** 2))
        alpha = np.maximum(alpha, ring * a * 0.55)
    col = np.array(color, np.float32)[None, None, :]
    return np.clip(arr * (1 - alpha[..., None]) + col * alpha[..., None], 0, 255)


def _foxing(arr: np.ndarray, rng: np.random.Generator, *, count: int = 90) -> np.ndarray:
    h, w = arr.shape[:2]
    layer = np.zeros((h, w, 3), np.float32)
    alpha = np.zeros((h, w), np.float32)
    for _ in range(max(0, count)):
        cx = int(rng.uniform(0, w))
        cy = int(rng.uniform(0, h))
        r = int(rng.uniform(1, max(2, min(w, h) // 180)))
        a = float(rng.uniform(0.15, 0.55))
        cv2.circle(layer, (cx, cy), r, (105, 70, 38), -1, lineType=cv2.LINE_AA)
        cv2.circle(alpha, (cx, cy), r + 1, a, -1, lineType=cv2.LINE_AA)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.2)[..., None]
    return np.clip(arr * (1 - alpha) + layer * alpha, 0, 255)


def _edge_darken(arr: np.ndarray, *, strength: float = 0.12, width: float = 0.05) -> np.ndarray:
    h, w = arr.shape[:2]
    xx = np.arange(w, dtype=np.float32)[None, :]
    yy = np.arange(h, dtype=np.float32)[:, None]
    d = np.minimum(np.minimum(xx, (w - 1) - xx), np.minimum(yy, (h - 1) - yy))
    mask = np.exp(-d / max(1.0, min(w, h) * width))
    return np.clip(arr * (1.0 - strength * mask[..., None]), 0, 255)


def _vignette(arr: np.ndarray, *, strength: float = 0.16) -> np.ndarray:
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx - w / 2) / max(1.0, w / 2)
    ny = (yy - h / 2) / max(1.0, h / 2)
    r = np.sqrt(nx * nx + ny * ny)
    mask = np.clip((r - 0.55) / 0.75, 0, 1) ** 1.4
    return np.clip(arr * (1.0 - strength * mask[..., None]), 0, 255)


def _folds(arr: np.ndarray, rng: np.random.Generator, *, count: int = 2) -> np.ndarray:
    h, w = arr.shape[:2]
    shadow = np.zeros((h, w), np.float32)
    light = np.zeros((h, w), np.float32)
    for i in range(max(0, count)):
        if i % 2 == 0:
            y = int(rng.uniform(h * 0.2, h * 0.8))
            cv2.line(shadow, (0, y), (w, y + int(rng.uniform(-5, 5))), 0.30, 2, cv2.LINE_AA)
            cv2.line(light, (0, y + 2), (w, y + 2 + int(rng.uniform(-5, 5))), 0.16, 2, cv2.LINE_AA)
        else:
            x = int(rng.uniform(w * 0.2, w * 0.8))
            cv2.line(shadow, (x, 0), (x + int(rng.uniform(-5, 5)), h), 0.26, 2, cv2.LINE_AA)
            cv2.line(light, (x + 2, 0), (x + 2 + int(rng.uniform(-5, 5)), h), 0.14, 2, cv2.LINE_AA)
    shadow = cv2.GaussianBlur(shadow, (0, 0), 2.2)[..., None]
    light = cv2.GaussianBlur(light, (0, 0), 2.2)[..., None]
    out = arr * (1.0 - shadow) + 255.0 * light
    return np.clip(out, 0, 255)


def _grid(arr: np.ndarray, *, step: int = 90, color: tuple[int, int, int] = (96, 116, 130),
          alpha: float = 0.16, vertical: bool = True, horizontal: bool = True) -> np.ndarray:
    h, w = arr.shape[:2]
    layer = np.zeros((h, w, 3), np.float32)
    mask = np.zeros((h, w), np.float32)
    if vertical:
        for x in range(0, w, max(8, step)):
            cv2.line(layer, (x, 0), (x, h), color, 1, cv2.LINE_AA)
            cv2.line(mask, (x, 0), (x, h), alpha, 1, cv2.LINE_AA)
    if horizontal:
        for y in range(0, h, max(8, step)):
            cv2.line(layer, (0, y), (w, y), color, 1, cv2.LINE_AA)
            cv2.line(mask, (0, y), (w, y), alpha, 1, cv2.LINE_AA)
    m = cv2.GaussianBlur(mask, (0, 0), 0.45)[..., None]
    return np.clip(arr * (1 - m) + layer * m, 0, 255)


def _halftone(arr: np.ndarray, *, step: int = 7, radius: int = 1,
              color: tuple[int, int, int] = (55, 48, 40), alpha: float = 0.13) -> np.ndarray:
    h, w = arr.shape[:2]
    layer = np.zeros((h, w, 3), np.float32)
    mask = np.zeros((h, w), np.float32)
    for y in range(0, h, max(3, step)):
        for x in range(0, w, max(3, step)):
            cv2.circle(layer, (x, y), max(1, radius), color, -1, cv2.LINE_AA)
            cv2.circle(mask, (x, y), max(1, radius), alpha, -1, cv2.LINE_AA)
    m = cv2.GaussianBlur(mask, (0, 0), 0.4)[..., None]
    return np.clip(arr * (1 - m) + layer * m, 0, 255)


def _rgba(arr: np.ndarray, alpha: np.ndarray | None = None) -> Image.Image:
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    if alpha is not None:
        a = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)
        im.putalpha(Image.fromarray(a, "L"))
    return im


def _torn_mask(w: int, h: int, rng: np.random.Generator, *, tear: float = 12.0) -> np.ndarray:
    pad = tear + 3
    pts: list[tuple[float, float]] = []
    n = max(18, int(w / 18))
    for i in range(n + 1):
        pts.append((pad + (w - 2 * pad) * i / n, pad + float(rng.uniform(-tear, tear * 0.4))))
    n = max(14, int(h / 18))
    for i in range(n + 1):
        pts.append((w - pad + float(rng.uniform(-tear * 0.4, tear)), pad + (h - 2 * pad) * i / n))
    for i in range(n + 1):
        pts.append((w - pad - (w - 2 * pad) * i / n, h - pad + float(rng.uniform(-tear * 0.4, tear))))
    for i in range(n + 1):
        pts.append((pad + float(rng.uniform(-tear, tear * 0.4)), h - pad - (h - 2 * pad) * i / n))
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).polygon(pts, fill=255)
    im = im.filter(ImageFilter.GaussianBlur(0.7))
    return np.asarray(im, np.float32) / 255.0


def _add_shadow(img: Image.Image, *, offset: tuple[int, int] = (8, 10), blur: int = 12,
                opacity: float = 0.32) -> Image.Image:
    pad = max(blur * 2, 12)
    w, h = img.size
    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    a = img.getchannel("A")
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.putalpha(a.point(lambda v: int(v * opacity)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow, (pad + offset[0], pad + offset[1]))
    canvas.alpha_composite(img, (pad, pad))
    return canvas


def _postcard(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    base = str(params.get("base", "#F4EBDD"))
    arr = _paper_base(w, h, rng, base, fibers=0.7, mottle=0.8)
    arr = _stains(arr, rng, count=int(params.get("stains", 4)), strength=0.10)
    arr = _edge_darken(arr, strength=0.10, width=0.04)
    im = _rgba(arr)
    d = ImageDraw.Draw(im)
    border = int(params.get("border", max(18, int(min(w, h) * 0.035))))
    d.rectangle([border, border, w - border - 1, h - border - 1], outline=(214, 203, 184, 255), width=max(1, border // 10))
    d.rectangle([border * 2, border * 2, w - border * 2, h - border * 2], outline=(226, 216, 198, 255), width=1)
    # stamp box (no text, just a perforated rectangle)
    sw, sh = int(w * 0.11), int(h * 0.09)
    sx, sy = w - border * 3 - sw, border * 3
    d.rectangle([sx, sy, sx + sw, sy + sh], outline=(170, 146, 112, 220), width=2)
    for i in range(1, 8):
        x = sx + sw * i / 8
        d.ellipse([x - 2, sy - 3, x + 2, sy + 1], fill=(244, 235, 221, 255))
    # postmark rings
    cx, cy = int(w * 0.78), int(h * 0.18)
    rr = int(min(w, h) * 0.055)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(110, 80, 56, 150), width=2)
    d.ellipse([cx - rr * 0.7, cy - rr * 0.7, cx + rr * 0.7, cy + rr * 0.7], outline=(110, 80, 56, 120), width=1)
    return im


def _poster(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    """Textless poster with a deliberately clean central text panel.

    Geometric blocks live in the margins; the centre stays quiet so Arabic or
    English text can be placed without a heavy blur. This is the procedural
    fallback for ``vintage_poster`` too.
    """
    base = str(params.get("base", "#E8D8B8"))
    arr = _paper_base(w, h, rng, base, fibers=0.7, mottle=0.9)
    im = _rgba(arr)
    d = ImageDraw.Draw(im, "RGBA")
    pal = palette_colors(style)
    papers = pal.get("paper") or [(244, 235, 221)]
    accents = pal.get("accent") or [(140, 47, 31), (201, 162, 39)]
    inks = pal.get("ink") or [(33, 30, 26)]

    top = int(h * 0.13)
    bottom = int(h * 0.87)
    # top/bottom printed bands, muted like screenprint ink
    d.rectangle([0, 0, w - 1, top], fill=accents[0] + (135,))
    d.rectangle([0, bottom, w - 1, h - 1], fill=inks[0] + (115,))
    d.rectangle([0, top + 5, w - 1, top + 9], fill=papers[0] + (120,))
    d.rectangle([0, bottom - 9, w - 1, bottom - 5], fill=papers[0] + (110,))

    # margin geometry (never inside the central 0.14..0.86 / 0.16..0.84 zone)
    for _ in range(3):
        if rng.random() < 0.5:
            cx = int(rng.choice([rng.uniform(w * 0.04, w * 0.13), rng.uniform(w * 0.87, w * 0.96)]))
            cy = int(rng.uniform(h * 0.18, h * 0.82))
        else:
            cx = int(rng.uniform(w * 0.16, w * 0.84))
            cy = int(rng.choice([rng.uniform(h * 0.02, h * 0.11), rng.uniform(h * 0.89, h * 0.98)]))
        rr = int(rng.uniform(min(w, h) * 0.035, min(w, h) * 0.085))
        c = accents[int(rng.integers(0, len(accents)))] + (int(rng.uniform(80, 145)),)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=c)

    # clean central panel with a thin double rule
    x0, y0 = int(w * 0.13), int(h * 0.16)
    x1, y1 = int(w * 0.87), int(h * 0.84)
    d.rectangle([x0, y0, x1, y1], fill=papers[0] + (205,))
    d.rectangle([x0, y0, x1, y1], outline=inks[0] + (95,), width=max(2, int(min(w, h) * 0.0025)))
    inset = max(8, int(min(w, h) * 0.012))
    d.rectangle([x0 + inset, y0 + inset, x1 - inset, y1 - inset],
                outline=accents[1] + (80,), width=1)

    arr2 = np.asarray(im.convert("RGB"), np.float32)
    arr2 = _folds(arr2, rng, count=2)
    arr2 = _edge_darken(arr2, strength=0.14, width=0.05)
    arr2 = _vignette(arr2, strength=0.18)
    return _rgba(arr2)


def _sticker(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    base = str(params.get("base", "#F4EBDD"))
    arr = _paper_base(w, h, rng, base, fibers=0.5, mottle=0.6)
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    pad = int(min(w, h) * 0.08)
    if rng.random() < 0.5:
        d.rounded_rectangle([pad, pad, w - pad, h - pad], radius=int(min(w, h) * 0.12), fill=255)
    else:
        d.ellipse([pad, pad, w - pad, h - pad], fill=255)
    a = np.asarray(mask.filter(ImageFilter.GaussianBlur(1.0)), np.float32) / 255.0
    # white die-cut border
    border = np.asarray(mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255.0
    im = _rgba(arr, np.clip(border, 0, 1))
    white = Image.new("RGBA", (w, h), (250, 247, 238, 255))
    im = Image.composite(white, im, Image.fromarray((np.clip(border - a, 0, 1) * 255).astype(np.uint8), "L"))
    im.putalpha(Image.fromarray((np.clip(border, 0, 1) * 255).astype(np.uint8), "L"))
    return im


def _label_tag(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    base = str(params.get("base", "#E8D8B8"))
    arr = _paper_base(w, h, rng, base, fibers=0.6, mottle=0.8)
    arr = _stains(arr, rng, count=2, strength=0.08)
    im = _rgba(arr)
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    pad = int(min(w, h) * 0.06)
    d.rounded_rectangle([pad, pad, w - pad, h - pad], radius=int(min(w, h) * 0.08), fill=255)
    hole = int(min(w, h) * 0.035)
    cx, cy = w // 2, pad + hole + int(min(w, h) * 0.05)
    d.ellipse([cx - hole, cy - hole, cx + hole, cy + hole], fill=0)
    a = np.asarray(mask.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255.0
    im.putalpha(Image.fromarray((a * 255).astype(np.uint8), "L"))
    return im


def _photo_frame(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    border = int(params.get("border", max(16, int(min(w, h) * 0.04))))
    d.rectangle([0, 0, w - 1, h - 1], fill=(250, 247, 238, 255))
    d.rectangle([border, border, w - border - 1, h - border - 1], fill=(0, 0, 0, 0))
    d.rectangle([border, border, w - border - 1, h - border - 1], outline=(214, 203, 184, 255), width=1)
    return im


def _halftone_overlay(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    layer = np.zeros((h, w, 3), np.float32)
    alpha = np.zeros((h, w), np.float32)
    step = int(params.get("dot", 7))
    radius = int(params.get("radius", 1))
    for y in range(0, h, max(3, step)):
        for x in range(0, w, max(3, step)):
            cv2.circle(layer, (x, y), max(1, radius), (40, 34, 28), -1, cv2.LINE_AA)
            cv2.circle(alpha, (x, y), max(1, radius), 0.22, -1, cv2.LINE_AA)
    return _rgba(layer, alpha)


def _fold_lines_overlay(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    layer = np.zeros((h, w, 3), np.float32)
    alpha = np.zeros((h, w), np.float32)
    for i in range(int(params.get("lines", 3))):
        if i % 2 == 0:
            y = int(rng.uniform(h * 0.15, h * 0.85))
            cv2.line(layer, (0, y), (w, y + int(rng.uniform(-8, 8))), (50, 42, 34), 2, cv2.LINE_AA)
            cv2.line(alpha, (0, y), (w, y + int(rng.uniform(-8, 8))), 0.35, 2, cv2.LINE_AA)
        else:
            x = int(rng.uniform(w * 0.15, w * 0.85))
            cv2.line(layer, (x, 0), (x + int(rng.uniform(-8, 8)), h), (50, 42, 34), 2, cv2.LINE_AA)
            cv2.line(alpha, (x, 0), (x + int(rng.uniform(-8, 8)), h), 0.35, 2, cv2.LINE_AA)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.4)
    return _rgba(layer, alpha)


def _vignette_overlay(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx - w / 2) / max(1.0, w / 2)
    ny = (yy - h / 2) / max(1.0, h / 2)
    r = np.sqrt(nx * nx + ny * ny)
    a = np.clip((r - 0.45) / 0.75, 0, 1) ** 1.3 * float(params.get("strength", 0.45))
    layer = np.zeros((h, w, 3), np.float32) + 18
    return _rgba(layer, a)


def _blueprint(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    base = np.zeros((h, w, 3), np.float32) + np.array([28, 52, 84], np.float32)
    n = _fractal(w, h, rng, scale=10, octaves=4)
    base += ((n - 0.5) * 14)[..., None]
    arr = _grid(base, step=int(params.get("step", 80)), color=(190, 216, 238), alpha=0.18)
    arr = _grid(arr, step=int(params.get("step", 80)) * 5, color=(220, 235, 245), alpha=0.10)
    arr = _edge_darken(arr, strength=0.22, width=0.06)
    arr = _vignette(arr, strength=0.24)
    return _rgba(arr)


def _seamless(w: int, h: int, rng: np.random.Generator, style: dict, params: dict) -> Image.Image:
    arr = _paper_base(w, h, rng, str(params.get("base", "#EFE3CF")), fibers=0.55, mottle=0.7)
    arr = _stains(arr, rng, count=int(params.get("stains", 5)), strength=0.10)
    arr = _vignette(arr, strength=0.08)
    return _rgba(arr)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

PROCEDURAL_KINDS = {
    "aged_paper", "parchment", "kraft_paper", "newsprint", "grid_paper", "lined_paper",
    "torn_paper", "paper_scrap", "tape_strip", "ink_stain", "postcard", "poster",
    "photo_frame", "halftone", "fold_lines", "vignette_overlay", "seamless_paper",
    "sticker", "label_tag", "blueprint",
}


def generate(kind: str, width: int, height: int, seed: int, style: dict) -> Image.Image:
    """Generate one RGBA asset deterministically."""
    if kind not in PROCEDURAL_KINDS:
        raise KeyError(f"Not a procedural kind: {kind}")
    spec = (style.get("kinds") or {}).get(kind) or {}
    params = dict(spec.get("params") or {})
    rng = np.random.default_rng(int(seed))
    w, h = int(width), int(height)

    if kind in ("aged_paper", "parchment", "kraft_paper"):
        base = str(params.get("base", "#EFE3CF"))
        arr = _paper_base(w, h, rng, base, fibers=float(params.get("fibers", 0.6)),
                          mottle=float(params.get("mottle", 0.8)))
        arr = _stains(arr, rng, count=int(params.get("stains", 8)),
                      strength=float(params.get("stain_strength", 0.16)))
        arr = _foxing(arr, rng, count=int(params.get("foxing", 70)))
        arr = _folds(arr, rng, count=int(params.get("folds", 2)))
        arr = _edge_darken(arr, strength=float(params.get("edge", 0.13)), width=0.05)
        arr = _vignette(arr, strength=float(params.get("vignette", 0.16)))
        if params.get("deckle"):
            mask = _torn_mask(w, h, rng, tear=float(params.get("tear", 10)))
            return _add_shadow(_rgba(arr, mask), offset=(5, 7), blur=8, opacity=0.24)
        return _rgba(arr)

    if kind == "newsprint":
        base = str(params.get("base", "#D8D2C4"))
        arr = _paper_base(w, h, rng, base, fibers=0.85, mottle=0.9)
        arr = _stains(arr, rng, count=int(params.get("stains", 6)), strength=0.12)
        arr = _halftone(arr, step=int(params.get("halftone_step", 7)),
                        radius=int(params.get("halftone_radius", 1)),
                        alpha=float(params.get("halftone_alpha", 0.10)))
        arr = _foxing(arr, rng, count=40)
        arr = _edge_darken(arr, strength=0.12, width=0.05)
        arr = _vignette(arr, strength=0.12)
        return _rgba(arr)

    if kind == "grid_paper":
        arr = _paper_base(w, h, rng, str(params.get("base", "#F2EBDD")), fibers=0.5, mottle=0.5)
        arr = _grid(arr, step=int(params.get("step", 90)), alpha=float(params.get("grid_alpha", 0.14)))
        arr = _edge_darken(arr, strength=0.08, width=0.05)
        return _rgba(arr)

    if kind == "lined_paper":
        arr = _paper_base(w, h, rng, str(params.get("base", "#F2EBDD")), fibers=0.5, mottle=0.5)
        arr = _grid(arr, step=int(params.get("step", 86)), alpha=float(params.get("line_alpha", 0.13)),
                    vertical=False, horizontal=True)
        arr = _edge_darken(arr, strength=0.08, width=0.05)
        return _rgba(arr)

    if kind in ("torn_paper", "paper_scrap"):
        arr = _paper_base(w, h, rng, str(params.get("base", "#F4EBDD")), fibers=0.7, mottle=0.8)
        arr = _stains(arr, rng, count=int(params.get("stains", 3)), strength=0.08)
        arr = _folds(arr, rng, count=int(params.get("folds", 1)))
        mask = _torn_mask(w, h, rng, tear=float(params.get("tear", 12)))
        im = _rgba(arr, mask)
        if params.get("shadow", True):
            im = _add_shadow(im, offset=(7, 9), blur=10, opacity=0.28)
        return im

    if kind == "tape_strip":
        base = np.array(hex_rgb(str(params.get("base", "#D9C79A"))), np.float32)
        arr = np.zeros((h, w, 3), np.float32) + base
        n = _fractal(w, h, rng, scale=12, octaves=4)
        arr += ((n - 0.5) * 12)[..., None]
        mask = np.ones((h, w), np.float32)
        edge = max(2, int(min(w, h) * 0.03))
        for i in range(w):
            if i < edge:
                mask[:, i] *= i / edge
            if i > w - edge:
                mask[:, i] *= (w - i) / edge
        for j in range(h):
            if j < edge:
                mask[j, :] *= j / edge
            if j > h - edge:
                mask[j, :] *= (h - j) / edge
        mask *= float(params.get("alpha", 0.55))
        return _rgba(arr, mask)

    if kind == "ink_stain":
        layer = np.zeros((h, w, 3), np.float32) + np.array(hex_rgb(str(params.get("color", "#3A2A1E"))), np.float32)
        alpha = np.zeros((h, w), np.float32)
        yy, xx = np.mgrid[0:h, 0:w]
        for _ in range(int(params.get("blobs", 5))):
            cx = float(rng.uniform(w * 0.2, w * 0.8))
            cy = float(rng.uniform(h * 0.2, h * 0.8))
            r = float(rng.uniform(min(w, h) * 0.05, min(w, h) * 0.22))
            m = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r)))
            alpha = np.maximum(alpha, m * float(rng.uniform(0.25, 0.65)))
        alpha = cv2.GaussianBlur(alpha, (0, 0), 2.0) * float(params.get("alpha", 0.55))
        return _rgba(layer, alpha)

    if kind == "postcard":
        return _postcard(w, h, rng, style, params)

    if kind == "poster":
        return _poster(w, h, rng, style, params)

    if kind == "photo_frame":
        return _photo_frame(w, h, rng, style, params)

    if kind == "halftone":
        return _halftone_overlay(w, h, rng, style, params)

    if kind == "fold_lines":
        return _fold_lines_overlay(w, h, rng, style, params)

    if kind == "vignette_overlay":
        return _vignette_overlay(w, h, rng, style, params)

    if kind == "seamless_paper":
        return _seamless(w, h, rng, style, params)

    if kind == "sticker":
        return _sticker(w, h, rng, style, params)

    if kind == "label_tag":
        return _label_tag(w, h, rng, style, params)

    if kind == "blueprint":
        return _blueprint(w, h, rng, style, params)

    raise KeyError(kind)
