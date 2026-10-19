# -*- coding: utf-8 -*-
"""Stage 1: render one scene through the Python API with a region plan.

Why the Python API instead of the CLI? The CLI reads the region JSON with the
system locale encoding (charmap on this Windows PC), which breaks any Arabic
text inside the file. The API lets us read UTF-8 ourselves and hand the engine
a fully parsed plan. This is also the API our automated pipeline will use.
"""
import os
import time

from whiteboard_animator import Scene, SnippetRegionPlan, render_video

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    img = os.path.join(HERE, "scene_ar.png")
    audio = os.path.join(HERE, "voice_test.wav")
    regions_path = os.path.join(HERE, "scene_ar.regions.json")
    out = os.path.join(HERE, "scene_ar_regions.mp4")

    with open(regions_path, encoding="utf-8") as f:
        plan = SnippetRegionPlan.model_validate_json(f.read())
    print("plan loaded:", len(plan.regions), "regions; idea:", plan.idea)

    t0 = time.perf_counter()
    durations = render_video(
        [Scene(img, audio=audio, region_plan=plan)],
        out,
        quality="high",
    )
    dt = time.perf_counter() - t0

    print("OUT =", out)
    print("SCENE_DURATIONS =", [round(d, 2) for d in durations])
    print("RENDER_SECONDS =", round(dt, 1))


if __name__ == "__main__":
    main()
