# -*- coding: utf-8 -*-
"""Stage 1 test: build doodle scenes (Arabic + English) that match the
whiteboard-animator input rules: ink on white, thick black outlines,
flat solid colors, lots of empty space, no gradients/shadows.

Arabic note: this Pillow build has no libraqm (no native shaping/bidi),
so Arabic text is shaped with arabic-reshaper + python-bidi before drawing.
This is the exact mechanism our final pipeline will use for Arabic titles.
"""
import os
from PIL import Image, ImageDraw, ImageFont
from PIL import features

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1280, 720
BLACK = (25, 25, 25)
BLUE = (66, 133, 199)
ORANGE = (240, 130, 40)
GREEN = (70, 160, 90)


def get_font(size):
    for name in ("tahoma.ttf", "tahomabd.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(rf"C:\Windows\Fonts\{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def shape_arabic(text):
    """Return display-ready Arabic text (shaped + reordered)."""
    if features.check("raqm"):
        return text  # Pillow can shape natively
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(text))


def draw_title(d, text, font, rtl):
    kwargs = {}
    shaped = shape_arabic(text) if rtl else text
    if rtl and features.check("raqm"):
        kwargs = dict(direction="rtl", language="ar")
    bbox = d.textbbox((0, 0), shaped, font=font, **kwargs)
    tw = bbox[2] - bbox[0]
    x = (W - tw) // 2 - bbox[0]
    y = 50 - bbox[1]
    d.text((x, y), shaped, font=font, fill=BLACK, **kwargs)


def draw_shapes(d):
    # building (blue, flat)
    d.rounded_rectangle((120, 360, 320, 620), radius=6, outline=BLACK, width=9, fill=BLUE)
    for bx, by in ((160, 410), (240, 410), (160, 500), (240, 500)):
        d.rectangle((bx, by, bx + 40, by + 40), outline=BLACK, width=7, fill="white")
    d.rectangle((205, 550, 245, 620), outline=BLACK, width=7, fill="white")

    # map pin (orange, flat)
    d.ellipse((430, 380, 570, 520), outline=BLACK, width=9, fill=ORANGE)
    d.polygon([(452, 470), (548, 470), (500, 615)], fill=ORANGE, outline=BLACK)
    d.line((430, 445, 570, 445), fill=BLACK, width=9)
    d.ellipse((475, 425, 525, 475), outline=BLACK, width=7, fill="white")

    # coin (green, flat)
    d.ellipse((700, 400, 860, 560), outline=BLACK, width=9, fill=GREEN)
    d.ellipse((745, 445, 815, 515), outline=BLACK, width=7)

    # up arrow (code-drawn detail)
    d.line((1010, 620, 1010, 430), fill=BLACK, width=10)
    d.line((1010, 430, 972, 472), fill=BLACK, width=10)
    d.line((1010, 430, 1048, 472), fill=BLACK, width=10)

    # check mark
    d.line((915, 640, 945, 672), fill=BLACK, width=11)
    d.line((945, 672, 1000, 585), fill=BLACK, width=11)


def main():
    font = get_font(58)
    scenes = [
        ("scene_ar.png", "ليه تشتري على الخريطة؟", True),
        ("scene_en.png", "Why buy on the map?", False),
    ]
    for fname, title, rtl in scenes:
        img = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(img)
        draw_title(d, title, font, rtl)
        draw_shapes(d)
        path = os.path.join(HERE, fname)
        img.save(path)
        print("saved:", path)
    print("RAQM_SUPPORT =", features.check("raqm"))


if __name__ == "__main__":
    main()
