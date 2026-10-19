# -*- coding: utf-8 -*-
"""Style comparison round 3b — same 5 jobs as round 3, but with the FIXED
background cleaner (gen/imglib.py) and raw images always saved.

Round 3 was destroyed by a flood-fill bug (neighbor-vs-neighbor comparison
leaked through gradients and whited out the whole image). The cleaner now
compares every pixel against the corner reference color and skips corners
that are not flat. Raw PNGs are kept in raw/ so cleanup can be re-tuned
without regenerating anything.

Usage (project root):
    .venv-gen\\Scripts\\python.exe gen\\test_styles.py
"""
import os
import sys
import time

import torch
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imglib import clean_to_white, snap_white  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "test", "styles3")
RAW_DIR = os.path.join(OUT_DIR, "raw")
MODEL_ID = "stable-diffusion-v1-5/stable-diffusion-v1-5"
WIDTH = HEIGHT = 512
STEPS = 15
GUIDANCE = 7.0
SEED = 1000

NEGATIVE = (
    "watermark, signature, text, words, letters, photograph, photo, "
    "realistic, 3d render, shading, shadow, gradient, texture, sky, clouds, "
    "ground, grass, landscape, scenery, background, room, interior, "
    "furniture, frame, border, multiple objects, blurry, messy, complex"
)

P1 = (
    "clipart, simple flat vector illustration, thick black outline, "
    "flat color fill, pure white background, minimalist, no text"
)
P2 = (
    "simple flat illustration, bold black outline, flat color fill, "
    "isolated single object, centered, plain white background, minimal, "
    "no text"
)
P3 = (
    "flat design clipart on a pure white background, bold black outline, "
    "bright flat colors, simple shapes, minimal icon, no background "
    "scenery, no text"
)

HOUSE = "a single cozy house with a pitched roof and one chimney"
HANDSHAKE = "two hands in a handshake"
KEY = "a single classic key with a round head and two teeth"

JOBS = [
    ("P1_house", HOUSE, P1),
    ("P2_house", HOUSE, P2),
    ("P3_house", HOUSE, P3),
    ("P2_handshake", HANDSHAKE, P2),
    ("P1_key", KEY, P1),
]


def main():
    torch.set_num_threads(os.cpu_count() or 4)
    from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler

    pipe = AutoPipelineForText2Image.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float32,
        variant="fp16",
        safety_checker=None,
        requires_safety_checker=False,
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe.set_progress_bar_config(disable=True)
    print("pipeline ready | seed:", SEED, "| steps:", STEPS)

    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)
    t0 = time.time()
    made = []
    for label, subject, style in JOBS:
        gen = torch.Generator(device="cpu").manual_seed(SEED)
        raw = pipe(
            prompt=f"{subject}, {style}",
            negative_prompt=NEGATIVE,
            width=WIDTH,
            height=HEIGHT,
            num_inference_steps=STEPS,
            guidance_scale=GUIDANCE,
            clip_skip=2,
            generator=gen,
        ).images[0]
        raw.save(os.path.join(RAW_DIR, f"{label}.png"))
        cleaned, flooded, white = clean_to_white(raw)
        png = os.path.join(OUT_DIR, f"{label}.png")
        cleaned.save(png)
        made.append((label, png))
        print(
            f"{label}: {time.time() - t0:.0f}s | flooded {flooded * 100:.0f}% "
            f"| white {white * 100:.0f}%",
            flush=True,
        )

    th = 512
    sheet = Image.new("RGB", (th * 3 + 40, th * 2 + 60), "white")
    dr = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for i, (label, png) in enumerate(made):
        r, c = divmod(i, 3)
        x, y = 10 + c * (th + 10), 10 + r * (th + 30)
        sheet.paste(Image.open(png).convert("RGB"), (x, y))
        dr.text((x + 4, y + th + 4), label, fill="black")
    sheet_path = os.path.join(OUT_DIR, "_sheet.png")
    sheet.save(sheet_path)
    print("sheet:", sheet_path)
    print("done in", round((time.time() - t0) / 60, 1), "min")


if __name__ == "__main__":
    main()
