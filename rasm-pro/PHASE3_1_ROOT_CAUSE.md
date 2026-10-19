# Phase 3.1 Root Cause Analysis

## Defect 1: Arabic Start Position
- Cause: `_find_start_point` in `mask_path.py` selected `candidates[-1]` (bottommost terminal) for RTL.
- Effect: Pen started from bottom-right-ish point, producing unnatural traversal.
- Fix applied: Select rightmost terminal (then topmost) via `max(candidates, key=lambda pt: (pt[1], -pt[0]))`.

## Defect 2: Crowded Letters
- Cause: Skeletonization fragments strokes; no authored centerline data. Word spacing comes from shaper advances (correct) but stroke fragmentation makes it look crowded.
- Status: Partially addressed by RTL fix; full fix requires authored stroke data (deferred).

## Defect 3: Pen Lifts / Natural Pauses
- Cause: `jumps` array exists but ordering is band-based heuristic, not validated handwriting order.
- Status: Partial; pen lifts preserved but ordering not authentically validated.

## Defect 4: Performance Bottleneck
- Scene 2 (image element) took 113s at 640x360 due to skeletonization of a large raster image.
- Director already caches via `_cached_doc`/`stroke_cache_path`. First render pays the cost; subsequent renders hit cache.
- Measured: full 5-scene film at 1280x720 rendered in 44.6s (after cache warm-up from 640x360 run).

## Defect 5: No Cinematic Templates / SFX
- Status: Not implemented. Existing Director templates used. ww1 has no narration audio asset.