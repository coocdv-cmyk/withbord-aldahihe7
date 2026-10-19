# -*- coding: utf-8 -*-
"""Cutout test: isolate the drawn object from ANY background with rembg
(u2net model — Apache-2.0 license, commercial-safe) and place it centered on
a pure white canvas.

Why: SD 1.5 base keeps painting full-bleed scenes and the occasional
degenerate background (colored noise). Instead of fighting the prompt, we let
the model draw freely and cut the salient object out programmatically.

No generation involved: this processes raw PNGs already saved from every
style round, so the verdict costs seconds, not hours.

Usage (project root):
    .venv-gen\\Scripts\\python.exe gen\\test_cutout.py
"""
import os
import sys
import time

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imglib import snap_white  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "test", "cutout")
CANVAS = 512
MARGIN = 56

RAW_CANDIDATES = [
    ("R1B_nopalette", "test/styles/B_clipart_nopalette.png"),
    ("R1C_doodle", "test/styles/C_doodle_palette.png"),
    ("R2E_icon", "test/styles2/E_icon.png"),
    ("R2H_cartoon", "test/styles2/H_cartoon_doodle.png"),
    ("R3P1_house", "test/styles3/raw/P1_house.png"),
    ("R3P2_house", "test/styles3/raw/P2_house.png"),
    ("R3P3_house", "test/styles3/raw/P3_house.png"),
    ("R3P2_handshake", "test/styles3/raw/P2_handshake.png"),
    ("R3P1_key", "test/styles3/raw/P1_key.png"),
]


def cutout_to_white(img, session, canvas=CANVAS, margin=MARGIN):
    """rembg cutout -> alpha bbox crop -> fit on white canvas -> snap white."""
    from rembg import remove

    rgba = remove(img.convert("RGB"), session=session)
    if rgba.mode != "RGBA":
        rgba = rgba.convert("RGBA")
    bbox = rgba.getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    w, h = rgba.size
    scale = min((canvas - 2 * margin) / w, (canvas - 2 * margin) / h)
    if scale < 1:
        rgba = rgba.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    white = Image.new("RGB", (canvas, canvas), "white")
    x = (canvas - rgba.width) // 2
    y = (canvas - rgba.height) // 2
    white.paste(rgba, (x, y), rgba)
    return snap_white(white, 250)


def main():
    from rembg import new_session

    t0 = time.time()
    print("loading u2net session (first run downloads ~176 MB model)...")
    session = new_session("u2net")
    print(f"session ready in {time.time() - t0:.0f}s")

    os.makedirs(OUT_DIR, exist_ok=True)
    made = []
    for label, rel in RAW_CANDIDATES:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print("missing, skipped:", rel)
            continue
        out = cutout_to_white(Image.open(path), session)
        png = os.path.join(OUT_DIR, f"{label}.png")
        out.save(png)
        made.append((label, png))
        print(f"{label}: done at {time.time() - t0:.0f}s", flush=True)

    if made:
        th = 250
        cols = 3
        rows = (len(made) + cols - 1) // cols
        from PIL import ImageDraw, ImageFont

        sheet = Image.new("RGB", (cols * th + 20, rows * (th + 26) + 20), "white")
        dr = ImageDraw.Draw(sheet)
        font = ImageFont.load_default()
        for i, (label, png) in enumerate(made):
            r, c = divmod(i, cols)
            im = Image.open(png).convert("RGB")
            im.thumbnail((th - 12, th - 12))
            x, y = 10 + c * th, 10 + r * (th + 26)
            sheet.paste(im, (x, y))
            dr.rectangle([x - 1, y - 1, x + th - 13, y + th - 13], outline="#ddd")
            dr.text((x + 2, y + th - 14), label, fill="black")
        sheet_path = os.path.join(OUT_DIR, "_sheet.png")
        sheet.save(sheet_path)
        print("sheet:", sheet_path)
    print("done in", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
