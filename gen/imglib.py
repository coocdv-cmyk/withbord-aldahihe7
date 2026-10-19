# -*- coding: utf-8 -*-
"""Shared image helpers for the element pipeline.

clean_to_white(): turns the flat background of a generated illustration into
pure white. The engine treats any pixel brighter than ~240 as background, so
this is what lets the drawing hand "discover" the element later.

Two lessons are baked into this version:
1. The flood must compare every candidate pixel against the REGION REFERENCE
   color (the corner color), never against its neighbor — comparing with the
   neighbor lets the fill leak across smooth gradients and eat the whole
   image.
2. If a corner patch is not flat (std too high), that corner is object/detail,
   not background — its flood is skipped.

A final guard reverts to the raw image if the fill swallowed more than 85% of
the pixels (safety net; should never trigger with a correct reference fill).
"""
from collections import deque

import numpy as np
from PIL import Image

TOL = 25          # per-channel max diff from the corner color
PATCH = 6         # corner patch half-size for the flatness/reference check
FLAT_STD = 30.0   # patch std above this = not a flat background corner
WHITE_THRESH = 240
REJECT_RATIO = 0.85


def snap_white(img, thresh=240):
    """Any near-white pixel becomes pure white (engine background threshold)."""
    arr = np.array(img.convert("RGB"))
    arr[arr.min(axis=2) >= thresh] = 255
    return Image.fromarray(arr)


def clean_to_white(img, tol=TOL, white_thresh=WHITE_THRESH):
    """Flood-fill each flat background corner region to pure white.

    Returns (image, flooded_ratio, white_ratio). flooded_ratio is the share of
    pixels the fill actually converted; white_ratio is the final near-white
    share of the whole image.
    """
    arr = np.array(img.convert("RGB")).astype(np.int16)
    h, w = arr.shape[:2]
    seen = np.zeros((h, w), dtype=bool)
    q = deque()

    def patch(y, x):
        y0, y1 = max(0, y - PATCH), min(h, y + PATCH + 1)
        x0, x1 = max(0, x - PATCH), min(w, x + PATCH + 1)
        return arr[y0:y1, x0:x1].reshape(-1, 3)

    refs = []
    for y0, x0 in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)):
        px = patch(y0, x0)
        if px.std(axis=0).max() > FLAT_STD:
            continue  # corner is detail, not flat background
        refs.append(px.mean(axis=0).round().astype(np.int16))

    if not refs:
        cleaned = snap_white(Image.fromarray(arr.astype(np.uint8)), white_thresh)
        wr = (np.array(cleaned).min(axis=2) >= white_thresh).mean()
        return cleaned, 0.0, wr

    for y0, x0 in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)):
        px = patch(y0, x0)
        if px.std(axis=0).max() > FLAT_STD:
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

    flooded_ratio = float(seen.mean())
    if flooded_ratio > REJECT_RATIO:
        out = arr.copy()  # guard: fill went rogue, keep raw pixels
    else:
        out = arr.copy()
        out[seen] = 255

    white = out.min(axis=2) >= white_thresh
    out[white] = 255
    return (
        Image.fromarray(out.astype(np.uint8)),
        flooded_ratio,
        float(white.mean()),
    )
