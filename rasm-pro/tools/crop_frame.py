"""قصّ مناطق نص من إطار + تكبير — للفحص البصري الدقيق."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

R = Path(r"D:\withbord inmation\rasm-pro")
qa = R / "qa"


def crop(im: Image.Image, box, scale, out):
    c = im.crop(box)
    w, h = c.size
    c.resize((int(w * scale), int(h * scale)), Image.LANCZOS).save(out)
    print("→", out, c.size, "×", scale)


im6 = Image.open(qa / "frames4" / "f_06.png")
print("f_06:", im6.size)
crop(im6, (520, 40, 945, 145), 4, qa / "crop6_label.png")
crop(im6, (470, 220, 945, 390), 4, qa / "crop6_caption.png")

im2 = Image.open(qa / "frames4" / "f_02.png")
print("f_02:", im2.size)
crop(im2, (60, 60, 900, 260), 2, qa / "crop2_title.png")
crop(im2, (60, 320, 900, 470), 2, qa / "crop2_sub.png")
