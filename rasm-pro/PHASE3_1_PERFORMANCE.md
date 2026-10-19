# Phase 3.1 Performance

## Before (Phase 3)
- Scene 2 at 640x360: 113.2s (skeletonization of raster image element).
- Full 5-scene film at 1280x720: hung (timeout).

## After (Phase 3.1)
- Full 5-scene film at 640x360: 14.3s (cache warm).
- Full 5-scene film at 1280x720: 44.6s (1069 frames, 24fps, 1.0x realtime-ish).
- Caching: `_cached_doc` + `stroke_cache_path` already present; first render pays skeletonization cost.

## Bottleneck
- Raster image skeletonization (`raster_to_strokes` → `thin` → `generate_mask_path`) dominates.
- Text elements are fast (~2-4s each).

## Recommendation
- Pre-cache stroke data at plan time; reuse across resolutions.
- Consider authored centerline data for common Arabic words to skip skeletonization entirely.