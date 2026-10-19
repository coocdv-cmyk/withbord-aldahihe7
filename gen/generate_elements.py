# -*- coding: utf-8 -*-
"""Local (CPU) generation of the element library — production version.

Pipeline per image: SD 1.5 (512px, DPM++ 15 steps, clip_skip=2) -> saved raw
-> background flood-filled to pure white (gen/imglib.py) -> snap near-white.

Prompt rules learned across 3 test rounds (do not "simplify" them back):
- CLIP truncates at 77 tokens: element description FIRST, style suffix after.
- "whiteboard" in the prompt becomes *content* (a physical whiteboard in a
  photoreal room) — it must never appear. Same for stock-art bait words.
- "(word:1.4)" weights are A1111 syntax; diffusers tokenizes them as garbage.
- clip_skip=2 keeps the output away from stock-photo watermarks.
- clipart/flat-vector wording + the flood-fill cleaner = flat doodle elements
  on pure white, ready for the engine's drawing animation.

Performance: ~2.2 minutes per image (measured). 28 elements x 2 variants =
56 images ≈ 2 hours, resumable (existing files are skipped).

Usage (from the project root):
    .venv-gen\\Scripts\\python.exe gen\\generate_elements.py
    .venv-gen\\Scripts\\python.exe gen\\generate_elements.py --only house key
    .venv-gen\\Scripts\\python.exe gen\\generate_elements.py --limit 1 --variants 1 --force
"""
import argparse
import csv
import os
import sys
import time

import torch
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imglib import clean_to_white  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "kaggle", "elements_list.csv")
OUT_DIR = os.path.join(ROOT, "elements", "batch1_local")
RAW_DIR = os.path.join(OUT_DIR, "raw")
SHEET_PATH = os.path.join(ROOT, "elements", "batch1_local_contact_sheet.png")

MODEL_ID = "stable-diffusion-v1-5/stable-diffusion-v1-5"
WIDTH = HEIGHT = 512
STEPS = 15
GUIDANCE = 7.0
VARIANTS = 2
BASE_SEED = 1000

# وصف العنصر بييجي الأول (قبل الستايل) عشان CLIP (77 توكين) ميقصّش الموضوع.
STYLE = (
    "clipart, simple flat vector illustration, thick black outline, "
    "flat color fill, pure white background, minimalist, no text"
)
# سلبيات قصيرة نضيفة — ممنوع أقواس/أوزان (diffusers مفيهاش ترجيح A1111).
NEGATIVE = (
    "watermark, signature, text, words, letters, photograph, photo, "
    "realistic, 3d render, shading, shadow, gradient, texture, sky, clouds, "
    "ground, grass, landscape, scenery, background, room, interior, "
    "furniture, frame, border, multiple objects, blurry, messy, complex"
)


def load_elements():
    with open(CSV_PATH, encoding="utf-8") as f:
        return [
            (r["id"].strip(), r["label_ar"].strip(), r["prompt_en"].strip())
            for r in csv.DictReader(f)
        ]


def build_sheet(elements, variants):
    have = [
        e for e in elements
        if os.path.exists(os.path.join(OUT_DIR, f"{e[0]}_v1.png"))
    ]
    if not have:
        return
    th = 260
    sheet = Image.new(
        "RGB", (variants * th + 20, len(have) * (th + 24) + 20), "white"
    )
    dr = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for r, (eid, _label, _p) in enumerate(have):
        for c in range(variants):
            p = os.path.join(OUT_DIR, f"{eid}_v{c + 1}.png")
            if not os.path.exists(p):
                continue
            im = Image.open(p).convert("RGB")
            im.thumbnail((th - 12, th - 12))
            x, y = 10 + c * th, 10 + r * (th + 24)
            sheet.paste(im, (x, y))
            dr.text((x + 2, y + th - 16), f"{eid} v{c + 1}", fill="black")
    sheet.save(SHEET_PATH)
    print("contact sheet:", SHEET_PATH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="element ids only")
    ap.add_argument("--limit", type=int, default=None, help="first N elements")
    ap.add_argument("--variants", type=int, default=VARIANTS)
    ap.add_argument("--steps", type=int, default=STEPS)
    ap.add_argument("--force", action="store_true", help="redo existing images")
    args = ap.parse_args()

    elements = load_elements()
    if args.only:
        wanted = set(args.only)
        elements = [e for e in elements if e[0] in wanted]
    if args.limit:
        elements = elements[: args.limit]
    if not elements:
        raise SystemExit("no elements selected")

    torch.set_num_threads(os.cpu_count() or 4)

    from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler

    print("model:", MODEL_ID)
    try:
        pipe = AutoPipelineForText2Image.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float32,
            variant="fp16",
            safety_checker=None,
            requires_safety_checker=False,
        )
    except Exception as exc:
        print("fp16 variant unavailable -> fallback:", exc)
        pipe = AutoPipelineForText2Image.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float32,
            safety_checker=None,
            requires_safety_checker=False,
        )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe.set_progress_bar_config(disable=True)
    print("model ready | scheduler: DPM++ | steps:", args.steps)

    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)
    total_imgs = len(elements) * args.variants
    made = 0
    t0 = time.time()

    for idx, (eid, label_ar, prompt_en) in enumerate(elements):
        for v in range(args.variants):
            out_png = os.path.join(OUT_DIR, f"{eid}_v{v + 1}.png")
            if os.path.exists(out_png) and not args.force:
                continue
            seed = BASE_SEED + idx * 100 + v
            gen = torch.Generator(device="cpu").manual_seed(seed)
            raw = pipe(
                prompt=f"{prompt_en}, {STYLE}",
                negative_prompt=NEGATIVE,
                width=WIDTH,
                height=HEIGHT,
                num_inference_steps=args.steps,
                guidance_scale=GUIDANCE,
                clip_skip=2,
                generator=gen,
            ).images[0]
            raw.save(os.path.join(RAW_DIR, f"{eid}_v{v + 1}.png"))
            cleaned, flooded, white = clean_to_white(raw)
            cleaned.save(out_png)
            made += 1
            elapsed = time.time() - t0
            per = elapsed / made
            left = per * (total_imgs - made)
            print(
                f"[{made}/{total_imgs}] {eid} v{v + 1} — {per:.0f}s/img "
                f"(flooded {flooded * 100:.0f}%, white {white * 100:.0f}%), "
                f"elapsed {elapsed / 60:.1f}m, left ~{left / 60:.1f}m",
                flush=True,
            )
        print(f"done element: {eid} ({label_ar})", flush=True)

    build_sheet(elements, args.variants)
    print("ALL DONE in", round((time.time() - t0) / 60, 1), "minutes | images made:", made)


if __name__ == "__main__":
    main()
