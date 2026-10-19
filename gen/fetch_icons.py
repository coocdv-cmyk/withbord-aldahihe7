# -*- coding: utf-8 -*-
"""Source 1 of the asset pipeline: professional line icons (Lucide, MIT).

Lucide's style is exactly our target: bold round-cap outlines on white.
That makes it the cleanest source for small scene objects (knife, cup,
wheat, moon, scales, ...). We download the Lucide icon set ONCE, then the
harvester picks what matches our asset list.

What it does:
1. (default) Downloads lucide.min.json (all icons as SVG path data, MIT)
   from the CDN into assets\raw\lucide\.
2. --probe: renders ~40 candidate icons to a contact sheet for visual QA.

Usage (project root):
    .venv\\Scripts\\python.exe gen\\fetch_icons.py
    .venv\\Scripts\\python.exe gen\\fetch_icons.py --probe
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW_DIR = os.path.join(ROOT, "assets", "raw", "lucide")
PROBE_DIR = os.path.join(ROOT, "assets", "probe", "lucide")

CDN = "https://cdn.jsdelivr.net/npm/lucide-static@latest/lucide.min.json"

# مرشحون مبدئيون لقائمة الأصول (اسم lucide)
PROBE_ICONS = [
    "shirt", "scissors", "key-round", "cloud-moon", "moon", "sun", "star",
    "sparkles", "droplets", "flame", "axed", "wind", "map-pin", "scale",
    "coins", "landmark", "menu", "wheat", "leaf", "trees", "mountain",
    "building", "landmark", "hourglass", "clock", "gauge", "compass",
    "footprints", "rabbit", "hand", "hand-metal", "heart-handshake",
    "users", "user", "user-round-plus", "baby", "package", "tent",
    "dice-1", "croissant", "lamp", "table", "utensils", "apple", "grape",
    "citrus", "cup-soda", "glass-water", "prison", "squirrel", "bird",
]

# أيقونات موجودة في lucideSTATIC نختبر تحميلها الآن
TEST_ICONS = ["shirt", "wheat", "moon"]


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def ensure_lucide_json():
    os.makedirs(RAW_DIR, exist_ok=True)
    dest = os.path.join(RAW_DIR, "lucide.min.json")
    if os.path.exists(dest):
        print("lucide.min.json already downloaded:", dest)
        return dest
    print("downloading lucide.min.json ...")
    data = http_get(CDN, timeout=120)
    with open(dest, "wb") as f:
        f.write(data)
    print("saved:", dest, f"({len(data) / 1024 / 1024:.1f} MB)")
    return dest


def fetch_single_icon(name):
    url = f"https://cdn.jsdelivr.net/npm/lucide-static@latest/icons/{name}.svg"
    try:
        return http_get(url, timeout=20).decode("utf-8")
    except Exception as exc:
        print(f"  ! {name}: {exc}")
        return None


def probe():
    dest = ensure_lucide_json()
    with open(dest, encoding="utf-8") as f:
        catalog = json.load(f)
    if isinstance(catalog, dict):
        names = list(catalog.keys())
    else:
        names = [it["name"] for it in catalog]
    print("total lucide icons:", len(names))
    import resvg_py

    os.makedirs(PROBE_DIR, None or PROBE_DIR, exist_ok=True)
    ok, miss = 0, []
    rows = []
    th = 128
    per_row = 10
    from PIL import Image, ImageDraw

    for name in PROBE_ICONS:
        svg_name = name if name in catalog else name
        svg = None
        if isinstance(catalog, dict) and svg_name in catalog:
            svg = catalog[svg_name]
        else:
            svg = fetch_single_icon(name)
        if not svg:
            miss.append(name)
            continue
        png_bytes = resvg_py.svg_to_bytes(svg_string=svg, width=140, height=140)
        with open(os.path.join(PROBE_DIR, f"{name}.png"), "wb") as f:
            f.write(bytes(png_bytes))
        ok += 1
    print(f"rendered {ok}, missing {len(miss)}: {miss[:8]}")
    # بناء اللوحة
    imgs = []
    for name in PROBE_ICONS:
        p = os.path.join(PROBE_DIR, f"{name}.png")
        if os.path.exists(p):
            imgs.append((name, Image.open(p).convert("RGBA")))
    cols = 8
    rows = (len(imgs) + cols - 1) // cols
    cw, chh = 160, 190
    sheet = Image.new("RGB", (cols * cw + 10, rows * chh + 10), "white")
    dr = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(imgs):
        r, c = divmod(i, cols)
        x, y = 5 + c * cw, 5 + r * chh
        sheet.paste(im, (x, y), im)
        dr.text((x + 2, y + 144), name[:18], fill="black")
    sheet_path = os.path.join(PROBE_DIR, "_sheet.png")
    sheet.save(sheet_path)
    print("probe sheet:", sheet_path)


def main():
    if "--probe" in sys.argv:
        probe()
    else:
        ensure_lucide_json()


if __name__ == "__main__":
    main()
