"""قياس أداء الرندر: رسم/كاميرا/كشف/ترميز — لتحديد الاختناق."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image  # noqa: E402

from engine.render.canvas import DocCursor, ImageReveal, Whiteboard, make_paper  # noqa: E402
from engine.render.camera import Viewport, crop_resize  # noqa: E402
from engine.strokes.model import Stroke  # noqa: E402


def stroke_from(points, brush=3.0):
    lengths = []
    total = 0.0
    prev = None
    for p in points:
        if prev is None:
            lengths.append(0.0)
        else:
            total += ((p[0] - prev[0]) ** 2 + (p[1] - prev[1]) ** 2) ** 0.5
            lengths.append(total)
        prev = p
    return Stroke(points=points, lengths=lengths, brush=brush)


def main() -> int:
    W, H = 2560, 1440
    t = time.time()
    paper = make_paper(W, H)
    print("paper:", round((time.time() - t) * 1000, 1), "ms")
    wb = Whiteboard(W, H, paper=paper)
    pts = [[200 + (i % 1200) * 1.5, 200 + (i // 1200) * 40 + (i % 7) * 3] for i in range(20000)]
    st = stroke_from(pts)
    cur = DocCursor([st])
    t = time.time()
    n = 0
    for k in range(60):
        segs = cur.advance((k + 1) / 60)
        wb.paint(segs)
        n += len(segs)
    dt = time.time() - t
    print(f"paint 60 chunk ({n} seg): {round(dt*1000,1)} ms → {round(dt/60*1000,2)} ms/إطار")

    t = time.time()
    for k in range(60):
        crop_resize(wb.rgb, Viewport(k * 3, k * 2, W - 200, H - 120), (960, 540))
    dt = time.time() - t
    print(f"crop_resize 60×: {round(dt*1000,1)} ms → {round(dt/60*1000,2)} ms/إطار")

    img = crop_resize(wb.rgb, Viewport(0, 0, W, H), (960, 540))
    t = time.time()
    for _ in range(60):
        img.tobytes()
    dt = time.time() - t
    print(f"tobytes 60×: {round(dt*1000,1)} ms → {round(dt/60*1000,2)} ms/إطار")

    im = Image.new("RGB", (900, 700), (120, 140, 160))
    rev = ImageReveal(im, [st], (100, 100, 900, 700))
    t = time.time()
    for k in range(60):
        rev.advance((k + 1) / 60)
        rev.blit(wb)
    dt = time.time() - t
    print(f"reveal 60×: {round(dt*1000,1)} ms → {round(dt/60*1000,2)} ms/إطار")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
