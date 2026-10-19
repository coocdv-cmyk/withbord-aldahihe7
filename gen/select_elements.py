# -*- coding: utf-8 -*-
"""Receive generated element batches and approve the chosen variants.

Works for the Kaggle zip (unzipped into elements/batch1) and the local CPU
batch (elements/batch1_local). Two modes:

1. Build a labeled contact sheet of what's in a folder:
       .venv\\Scripts\\python.exe gen\\select_elements.py --dir elements\\batch1
2. Approve variants (copies them into elements\\approved\\<id>.png):
       .venv\\Scripts\\python.exe gen\\select_elements.py --dir elements\\batch1 ^
           --choose house=v2 key=v1 handshake=v2

The approved library is what Stage 3 (scene composer) reads.
"""
import argparse
import glob
import os
import re
import shutil

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPROVED_DIR = os.path.join(ROOT, "elements", "approved")
NAME_RE = re.compile(r"^(?P<eid>[a-z0-9_]+)_v(?P<v>\d+)\.png$")


def scan(directory):
    found = {}
    for p in sorted(glob.glob(os.path.join(directory, "*.png"))):
        m = NAME_RE.match(os.path.basename(p))
        if not m:
            continue
        found.setdefault(m.group("eid"), []).append((int(m.group("v")), p))
    for eid in found:
        found[eid].sort()
    return found


def build_sheet(found, sheet_path, th=320):
    eids = sorted(found)
    if not eids:
        print("nothing to show in", sheet_path)
        return
    max_v = max(len(v) for v in found.values())
    sheet = Image.new("RGB", (max_v * th + 20, len(eids) * (th + 26) + 20), "white")
    dr = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for r, eid in enumerate(eids):
        for c, (v, p) in enumerate(found[eid]):
            im = Image.open(p).convert("RGB")
            im.thumbnail((th - 12, th - 12))
            x, y = 10 + c * th, 10 + r * (th + 26)
            sheet.paste(im, (x, y))
            dr.text((x + 2, y + th - 14), f"{eid} v{v}", fill="black")
    sheet.save(sheet_path)
    print("contact sheet:", sheet_path)
    print("elements found:", len(eids))


def approve(found, choices):
    os.makedirs(APPROVED_DIR, exist_ok=True)
    ok, bad = 0, []
    for choice in choices:
        if "=" not in choice:
            bad.append(choice)
            continue
        eid, _, vtxt = choice.partition("=")
        eid, vtxt = eid.strip(), vtxt.strip().lstrip("v")
        try:
            v = int(vtxt)
        except ValueError:
            bad.append(choice)
            continue
        variants = dict(found.get(eid, []))
        if v not in variants:
            bad.append(f"{eid}=v{v} (مش موجود)")
            continue
        dst = os.path.join(APPROVED_DIR, f"{eid}.png")
        shutil.copy(variants[v], dst)
        print("approved:", eid, f"= v{v}", "->", dst)
        ok += 1
    if bad:
        print("!! متجاهَل:", ", ".join(bad))
    print(f"approved {ok} element(s) | library now:", len(glob.glob(os.path.join(APPROVED_DIR, '*.png'))), "elements")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join("elements", "batch1"),
                    help="folder with <element>_v<N>.png files")
    ap.add_argument("--sheet", default=None, help="contact sheet path (default: <dir>/_sheet.png)")
    ap.add_argument("--choose", nargs="*", default=None,
                    help="e.g. house=v2 key=v1 (approved into elements/approved)")
    args = ap.parse_args()

    directory = args.dir if os.path.isabs(args.dir) else os.path.join(ROOT, args.dir)
    if not os.path.isdir(directory):
        raise SystemExit(f"folder not found: {directory}")

    found = scan(directory)
    if not found:
        raise SystemExit(f"no <element>_v<N>.png files in {directory}")

    if args.choose:
        approve(found, args.choose)

    sheet_path = args.sheet or os.path.join(directory, "_sheet.png")
    build_sheet(found, sheet_path)


if __name__ == "__main__":
    main()
