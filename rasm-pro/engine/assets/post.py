"""Post-processing and contact sheets for the Asset Studio."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .style import find_asset_font, palette_colors


def _with_alpha(rgb: np.ndarray, original: Image.Image) -> Image.Image:
    out = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    if original.mode in ("RGBA", "LA"):
        out.putalpha(original.getchannel("A"))
    return out


def resize_cover(img: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.fit(img.convert("RGBA"), (int(width), int(height)), method=Image.Resampling.LANCZOS)


def tone_to_palette(img: Image.Image, style: dict, *, strength: float = 0.55,
                    saturation_scale: float = 0.78) -> Image.Image:
    rgb = np.asarray(img.convert("RGB"), np.float32)
    pal = palette_colors(style)
    paper = pal.get("paper") or [(244, 235, 221), (201, 184, 150)]
    hi = np.array(paper[0], np.float32)
    lo = np.array(paper[-1], np.float32)
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    tone = lo[None, None, :] + gray[..., None] * (hi - lo)[None, None, :]
    out = rgb * (1.0 - strength) + tone * strength
    hsv = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * saturation_scale, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)
    return _with_alpha(out, img)


def cut_flat_background(img: Image.Image, *, tolerance: float = 18.0) -> Image.Image:
    """Cut a near-uniform border colour to alpha.

    Used only for SD1.5 collage/botanical elements prompted as "isolated on
    plain cream paper". It is intentionally conservative; QA still checks the
    alpha coverage and a human can reject the result.
    """
    arr = np.asarray(img.convert("RGB"), np.float32)
    h, w = arr.shape[:2]
    b = max(4, min(h, w) // 18)
    strips = np.concatenate([
        arr[:b, :, :].reshape(-1, 3),
        arr[-b:, :, :].reshape(-1, 3),
        arr[:, :b, :].reshape(-1, 3),
        arr[:, -b:, :].reshape(-1, 3),
    ], axis=0)
    bg = np.median(strips, axis=0)
    dist = np.sqrt(((arr - bg[None, None, :]) ** 2).sum(axis=2))
    low = max(1.0, float(tolerance) * 0.55)
    high = max(low + 1.0, float(tolerance) * 1.65)
    alpha = np.clip((dist - low) / (high - low), 0.0, 1.0)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.8)
    if img.mode in ("RGBA", "LA"):
        old = np.asarray(img.getchannel("A"), np.float32) / 255.0
        alpha = np.minimum(alpha, old)
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    out.putalpha(Image.fromarray((alpha * 255).astype(np.uint8), "L"))
    return out


def add_grain(img: Image.Image, *, amount: float = 3.2, seed: int = 7) -> Image.Image:
    arr = np.asarray(img.convert("RGB"), np.float32)
    rng = np.random.default_rng(seed)
    noise = (rng.random(arr.shape[:2], dtype=np.float32) - 0.5) * (amount * 2.0)
    arr = np.clip(arr + noise[..., None], 0, 255)
    return _with_alpha(arr, img)


def add_vignette(img: Image.Image, *, strength: float = 0.10) -> Image.Image:
    arr = np.asarray(img.convert("RGB"), np.float32)
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx - w / 2) / max(1.0, w / 2)
    ny = (yy - h / 2) / max(1.0, h / 2)
    r = np.sqrt(nx * nx + ny * ny)
    mask = np.clip((r - 0.55) / 0.75, 0, 1) ** 1.4
    return _with_alpha(arr * (1.0 - strength * mask[..., None]), img)


def clean_text_zone(img: Image.Image, zone: tuple[float, float, float, float], *,
                    max_busy: float = 0.14, paper_color: tuple[int, int, int] = (244, 235, 221),
                    strength: float = 0.72) -> tuple[Image.Image, dict]:
    """Reduce high-frequency clutter only inside the text-safe zone.

    This is a soft repair, not a painted rectangle: a blurred copy is blended
    through a feathered mask, and a little paper color is added. It preserves
    stains and large-scale paper character while making the text readable.
    """
    from .qa import text_zone_metrics

    before = text_zone_metrics(img, zone)
    if before["busy"] <= max_busy:
        return img, {"cleaned": False, "before": before, "after": before}

    arr = np.asarray(img.convert("RGB"), np.float32)
    h, w = arr.shape[:2]
    x, y, zw, zh = zone
    x0, y0 = max(0, int(round(x * w))), max(0, int(round(y * h)))
    x1, y1 = min(w, int(round((x + zw) * w))), min(h, int(round((y + zh) * h)))
    sigma = max(6.0, min(w, h) * 0.012)
    blurred = cv2.GaussianBlur(arr, (0, 0), sigma)
    clean = blurred * 0.68 + np.array(paper_color, np.float32)[None, None, :] * 0.32
    mask = np.zeros((h, w), np.float32)
    cv2.rectangle(mask, (x0, y0), (x1, y1), 1.0, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), max(8.0, min(w, h) * 0.018))
    a = (strength * mask)[..., None]
    out = arr * (1.0 - a) + clean * a
    fixed = _with_alpha(out, img)
    after = text_zone_metrics(fixed, zone)
    return fixed, {"cleaned": True, "before": before, "after": after}


def _font(size: int):
    path = find_asset_font()
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def contact_sheet(records: list[dict], out_path: str | Path, *, cols: int = 3,
                  thumb: tuple[int, int] = (560, 360)) -> Path:
    """Write a labelled review sheet. Records are metadata dicts with file/qa."""
    out_path = Path(out_path)
    if not records:
        raise ValueError("No records for contact sheet")
    tw, th = thumb
    label_h = 78
    pad = 18
    rows = (len(records) + cols - 1) // cols
    W = cols * tw + (cols + 1) * pad
    H = rows * (th + label_h) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    f_title = _font(22)
    f_small = _font(17)
    for i, rec in enumerate(records):
        r, c = divmod(i, cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + label_h + pad)
        try:
            im = Image.open(rec["file"]).convert("RGBA")
            im = ImageOps.contain(im, (tw, th), method=Image.Resampling.LANCZOS)
            bg = Image.new("RGBA", (tw, th), (236, 231, 220, 255))
            bg.alpha_composite(im, ((tw - im.width) // 2, (th - im.height) // 2))
            sheet.paste(bg.convert("RGB"), (x, y))
        except Exception:
            d.rectangle([x, y, x + tw, y + th], fill=(60, 60, 66))
        qa = rec.get("qa") or {}
        verdict = "PASS" if qa.get("pass") else "CHECK"
        color = (120, 220, 150) if qa.get("pass") else (255, 190, 90)
        d.text((x, y + th + 6), f"{rec.get('id', '?')}", font=f_title, fill=(245, 242, 232))
        d.text((x, y + th + 34), f"{rec.get('kind', '')} · {rec.get('method', '')} · {verdict} · {qa.get('score', 0)}",
               font=f_small, fill=color)
        d.text((x, y + th + 54), f"palette {qa.get('palette_distance', '?')} · busy {qa.get('text_zone', {}).get('busy', '?')}",
               font=f_small, fill=(180, 178, 170))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=92)
    return out_path
