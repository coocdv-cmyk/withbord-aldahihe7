# -*- coding: utf-8 -*-
"""Build kaggle/whiteboard-elements.ipynb from kaggle/elements_list.csv.

Usage (from the project root, with the project venv):
    .\\.venv\\Scripts\\python.exe kaggle\\make_notebook.py
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "elements_list.csv")
OUT_PATH = os.path.join(HERE, "whiteboard-elements.ipynb")


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text,
    }


def load_elements():
    rows = []
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(
                (
                    row["id"].strip(),
                    row["label_ar"].strip(),
                    row["prompt_en"].strip(),
                )
            )
    return rows


def elements_literal(rows) -> str:
    lines = ["ELEMENTS = ["]
    for eid, ar, en in rows:
        lines.append(f"    ({eid!r}, {ar!r}, {en!r}),")
    lines.append("]")
    return "\n".join(lines)


INTRO = """# توليد مكتبة العناصر — المرحلة 2 (وايت بورد)

النوت بوك ده بيولّد **مكتبة عناصر الرسمة الخطية** (بيت، مفتاح، خريطة...) كلها بنفس الستايل الأبيض والألوان المسطحة.

## قبل ما تشغّل
1. من إعدادات الجلسة (يمين): **Internet = On** و **Accelerator = GPU** (T4).
2. دوس **Run All** واستنى.

## الناتج
- `elements_batch.zip` — النسخ النهائية من كل عنصر (PNG بخلفية بيضا نضيفة).
- `contact_sheet_master.png` — لوحة معاينة واحدة تشوف فيها كل العناصر مع بعض.

> القائمة نفسها في `elements_list.csv`؛ ولو عدّلتها شغّل `kaggle\\make_notebook.py` تاني عشان يعيد بناء النوت بوك.
"""

CONFIG_TEMPLATE = """# ================= إعدادات التوليد =================
# الافتراضي: SD 1.5 — الأخف والأسرع والمتاح تجاريًا (رخصة OpenRAIL-M).
# لو حبيت جودة أعلى على كارت T4: بدّل لـ "stabilityai/stable-diffusion-xl-base-1.0" وخلي WIDTH/HEIGHT = 1024.
# تحذير: موديلات turbo أسرع بكتير بس رخصتها غير تجارية — متستخدمهاش لو فيه ربح.
MODEL_ID = "stable-diffusion-v1-5/stable-diffusion-v1-5"

# LoRA اختياري لتقوية ستايل الخطوط: حط لينك .safetensors مباشر (راجع رخصته قبل أي استخدام تجاري)
LORA_URL = ""
LORA_SCALE = 0.8

WIDTH = HEIGHT = 512    # للـ SDXL استخدم 1024
STEPS = 15
GUIDANCE = 7.0
VARIANTS = 2            # نسختين لكل عنصر عشان تختار الأحسن
BASE_SEED = 1000
OUT_DIR = "/kaggle/working/elements"

# قالب الستايل الموحّد — ميغيّرش أبدًا (ده سرّ الثبات بين كل العناصر والمشاهد).
# قواعد اتحصّلت بالتجربة العملية (متلغبطهاش):
# - وصف العنصر الأول وبعده الستايل، عشان CLIP (77 توكين) ميقصّش العنصر أبدًا.
# - كلمة "whiteboard" في البرومبت بتتحول لمحتوى (لوحة حائط في غرفة حقيقية) — ممنوعة.
# - صيغة الأوزان "(كلمة:1.4)" بتاعة A1111 ومش مدعومة في diffusers — بتتحول لتوكينات زبالة.
STYLE = (
    "clipart, simple flat vector illustration, thick black outline, "
    "flat color fill, pure white background, minimalist, no text"
)
NEGATIVE = (
    "watermark, signature, text, words, letters, photograph, photo, "
    "realistic, 3d render, shading, shadow, gradient, texture, sky, clouds, "
    "ground, grass, landscape, scenery, background, room, interior, "
    "furniture, frame, border, multiple objects, blurry, messy, complex"
)

__ELEMENTS__
"""

INSTALL = """# تنزيل المكتبات المطلوبة (دقيقة تقريبًا)
# ملاحظة: transformers مثبّت على 4.x — نسخة 5.x شالت البنية الداخلية اللي
# diffusers بيستخدمها في clip_skip (باج حقيقي بين النسختين، اتأكدنا منه محليًا).
# diffusers<0.36 عشان يفضل متوافق مع transformers 4.x و huggingface-hub 0.3x.
!pip -q install "diffusers>=0.35,<0.36" "transformers>=4.45,<5" "accelerate>=1.0.0" "peft>=0.13.0" "safetensors>=0.4.0" requests
print("installs done")
"""

LOAD = '''import os
from pathlib import Path

import requests
import torch
from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
else:
    print("!! مفيش GPU — افتح Settings واختار Accelerator = GPU وشغّل تاني")

dtype = torch.float16 if torch.cuda.is_available() else torch.float32
try:
    pipe = AutoPipelineForText2Image.from_pretrained(MODEL_ID, torch_dtype=dtype, variant="fp16")
except Exception as exc:
    print("fp16 variant not available, falling back:", exc)
    pipe = AutoPipelineForText2Image.from_pretrained(MODEL_ID, torch_dtype=dtype)
pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")

# نفس محسّن الرسم بتاع النسخة المحلية — جودة عالية بخطوات أقل
pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)

if LORA_URL:
    lora_path = Path("/kaggle/working/style_lora.safetensors")
    resp = requests.get(LORA_URL, timeout=600)
    resp.raise_for_status()
    lora_path.write_bytes(resp.content)
    pipe.load_lora_weights(str(lora_path))
    try:
        pipe.fuse_lora(lora_scale=LORA_SCALE)
    except Exception as exc:
        print("fuse skipped:", exc)
    print("LoRA loaded:", LORA_URL)

pipe.set_progress_bar_config(disable=True)
print("pipeline ready | scheduler: DPM++")
'''

GENERATE = '''import json
import os
import time
from collections import deque

import numpy as np
from PIL import Image


def clean_to_white(img, tol=25, white_thresh=240):
    """توسيع من الحواف الأربعة: أي خلفية مسطحة ملتصقة بالحدود تتحول أبيض نقي،
    وبعدها أي بكسل شبه أبيض يتثبّت (المحرك بيعتبر أي حاجة أفتح من 240 خلفية).

    القاعدة الذهبية: كل بكسل بيتقارن بلون مرجع الحافة نفسه — مش بالجار —
    عشان التوسيع ميسرّبش جوه الرسمة. ولو الكورنر فيه تفاصيل (مش لون مسطح)
    بنتخطاه. وفي الآخر حماية: لو التوسيع تهم أكتر من 85% من الصورة نرفضه.
    """
    arr = np.array(img.convert("RGB")).astype(np.int16)
    h, w = arr.shape[:2]
    seen = np.zeros((h, w), dtype=bool)
    q = deque()

    def patch(y, x, p=6):
        y0, y1 = max(0, y - p), min(h, y + p + 1)
        x0, x1 = max(0, x - p), min(w, x + p + 1)
        return arr[y0:y1, x0:x1].reshape(-1, 3)

    for y0, x0 in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)):
        px = patch(y0, x0)
        if px.std(axis=0).max() > 30:   # الكورنر فيه تفاصيل = مش خلفية مسطحة
            continue
        if seen[y0, x0]:
            continue
        ref = px.mean(axis=0).round().astype(np.int16)
        seen[y0, x0] = True
        q.append((y0, x0))
        while q:
            y, x = q.popleft()
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx]:
                    if np.abs(arr[ny, nx] - ref).max() <= tol:
                        seen[ny, nx] = True
                        q.append((ny, nx))

    out = arr.copy()
    if seen.mean() <= 0.85:
        out[seen] = 255
    white = out.min(axis=2) >= white_thresh
    out[white] = 255
    return Image.fromarray(out.astype(np.uint8))


os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(OUT_DIR + "/raw", exist_ok=True)
meta = []
t0 = time.time()
device = "cuda" if torch.cuda.is_available() else "cpu"

for idx, (eid, label_ar, prompt_en) in enumerate(ELEMENTS):
    full_prompt = f"{prompt_en}, {STYLE}"
    for v in range(VARIANTS):
        seed = BASE_SEED + idx * 100 + v
        gen = torch.Generator(device=device).manual_seed(seed)
        image = pipe(
            prompt=full_prompt,
            negative_prompt=NEGATIVE,
            width=WIDTH,
            height=HEIGHT,
            num_inference_steps=STEPS,
            guidance_scale=GUIDANCE,
            clip_skip=2,
            generator=gen,
        ).images[0]
        image.save(f"{OUT_DIR}/raw/{eid}_v{v + 1}.png")
        clean_to_white(image).save(f"{OUT_DIR}/{eid}_v{v + 1}.png")
        meta.append({"id": eid, "variant": v + 1, "seed": seed, "prompt": full_prompt})
    print(f"[{idx + 1}/{len(ELEMENTS)}] {eid} ({label_ar}) — {time.time() - t0:.0f}s elapsed")

with open("/kaggle/working/elements_meta.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)

print("GENERATION DONE:", len(meta), "images in", round(time.time() - t0), "seconds")
'''

SHEETS = '''import glob
import os
import shutil

from PIL import Image, ImageDraw, ImageFont

TH = 260
cols = VARIANTS
rows = len(ELEMENTS)
sheet = Image.new("RGB", (cols * TH + 20, rows * (TH + 24) + 20), "white")
dr = ImageDraw.Draw(sheet)
font = ImageFont.load_default()

for r, (eid, label_ar, _) in enumerate(ELEMENTS):
    for c in range(VARIANTS):
        p = os.path.join(OUT_DIR, f"{eid}_v{c + 1}.png")
        im = Image.open(p).convert("RGB")
        im.thumbnail((TH - 12, TH - 12))
        x = 10 + c * TH
        y = 10 + r * (TH + 24)
        sheet.paste(im, (x, y))
        dr.text((x + 2, y + TH - 16), f"{eid} v{c + 1}", fill="black")

sheet.save("/kaggle/working/contact_sheet_master.png")

# الزيب فيه الصور النهائية بس (من غير مجلد raw)
final_dir = "/kaggle/working/elements_final"
shutil.rmtree(final_dir, ignore_errors=True)
os.makedirs(final_dir, exist_ok=True)
for p in glob.glob(os.path.join(OUT_DIR, "*.png")):
    shutil.copy(p, final_dir)

shutil.make_archive("/kaggle/working/elements_batch", "zip", "/kaggle/working", "elements_final")

print("== جاهز للتنزيل ==")
print("/kaggle/working/elements_batch.zip")
print("/kaggle/working/contact_sheet_master.png")
print("عدد الصور:", len(ELEMENTS) * VARIANTS)
'''

NEXT = """## خلصت التوليد — الخطوة الجاية

1. من **Output** في يمين الشاشة (أو تبويب Data / Output تحت): نزّل:
   - `elements_batch.zip`
   - `contact_sheet_master.png`
2. فك ضغط الـ zip في مجلد `D:\\withbord inmation\\elements\\batch1\\` على جهازك.
3. افتح لوحة `contact_sheet_master.png` واختار النسخة الأحسن لكل عنصر.
4. قول للاسيستنت **"وصل"** — وهو هيعمل سكريبت الاستلام والاختيار وينقل المختار لمكتبة `elements/approved/`.

> عايز تعدّل عنصر أو تضيف عناصر؟ عدّل `ELEMENTS` في خلية الإعدادات وشغّل خلايا التوليد + اللوحة تاني بس.
""" + "\n"


def main():
    rows = load_elements()
    assert rows, "elements_list.csv is empty"
    config = CONFIG_TEMPLATE.replace("__ELEMENTS__", elements_literal(rows))
    notebook = {
        "cells": [
            md(INTRO),
            code(config),
            code(INSTALL),
            code(LOAD),
            code(GENERATE),
            code(SHEETS),
            md(NEXT),
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(notebook, f, ensure_ascii=False, indent=1)
    print("wrote:", OUT_PATH)
    print("elements:", len(rows))


if __name__ == "__main__":
    main()
