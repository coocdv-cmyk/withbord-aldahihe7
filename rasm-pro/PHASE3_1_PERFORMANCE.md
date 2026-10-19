# Phase 3.1 — Performance Report (profiling, cache, verified optimisation)

All figures are reproducible from the committed tools; raw data in `qa/phase31_perf/`
(`perf.json`, `profile_raster.txt`).

```powershell
$env:PYTHONUTF8='1'; .venv\Scripts\python.exe tools\perf_phase31.py thinning   # thinning + raster trace
$env:PYTHONUTF8='1'; .venv\Scripts\python.exe tools\perf_phase31.py text       # text pipeline cold/warm
$env:PYTHONUTF8='1'; .venv\Scripts\python.exe tools\perf_phase31.py scene      # 5-scene prep cold/warm
$env:PYTHONUTF8='1'; .venv\Scripts\python.exe tools\perf_raster_profile.py     # cProfile of the tracer
```

## 1. Headline: where the time went, and what changed

| work item | before | after | speed-up |
|---|---|---|---|
| `raster_to_strokes` — real 900 px ww1 photo (2.61 M px mask) | **111.4 s** | **7.39 s** | **15.1×** |
| full cProfile of the same trace | **118.9 s** | **8.56 s** | **13.9×** |
| cold prep of the 5 ww1 v2 scenes (3 photos + all text, empty cache) | **650.4 s** | **48.5 s** | **13.4×** |
| warm prep of the same 5 scenes (cache hit) | 3.19 s | 3.08 s | — |
| text pipeline, 3 × 200 pt sentences (cold → warm) | 19.06 s → 0.35 s (54×) | unchanged | — |
| film render (1956 frames, 1280×720, SFX mux) | — | **173.0 s** (final render, after the sub-label change) / **90.9 s** (earlier warm-cache render, ≈21.5 fps) | — |

Memory (tracemalloc, peaks): scene prep cold **55.5 MB**, warm **23.9 MB**; text pipeline cold 22.5 MB,
warm 15.4 MB. The film's 81.5 s at 24 fps is 1956 frames; encoding runs through the bundled FFmpeg
(`studio/runtime`, 9.0.2, `-fps_mode` compatible).

## 2. Bottleneck profile (before)

`qa/phase31_perf/profile_raster.txt`, `tools/perf_raster_profile.py`:

```text
3956192 function calls … 118.9 s total          (before; call count = after-profile total, before-profile total was not saved)
  113.8 s  generate_mask_path          (95.7 %)
  110.7 s  ├─ _find_start_point        (cum.)
   87.3 s  │   └─ _count_neighbours    47.5 M calls, pure-Python 8-neighbour count
```

`_count_neighbours` was called for candidate pixels while walking the thinned mask, and
`_find_start_point` scanned the whole Python set of remaining pixels for every traced component.
Both are **O(pixels)** per step in Python.

## 3. Optimisation (output-identical)

`engine/strokes/mask_path.py`:

1. `class _Mask` — wraps the boolean mask and keeps an `int32` **neighbour-count plane**. It is built
   vectorised (8 shifted copies summed, `px` excluded), then maintained in O(1) per clear: clearing
   `(y, x)` decrements the 3×3 block and re-adds the pixel's own decrement (a pixel is not its own
   neighbour — this subtlety is what the equivalence tests caught; see RC4 in `PHASE3_1_ROOT_CAUSE.md`).
2. `_find_start_point` uses `np.nonzero` on the remaining-mask instead of a Python scan.
3. `_find_near_point`, `_trace_from_point`, `generate_mask_path` accept `_Mask`.
4. `_count_neighbours` is kept unchanged as the reference implementation used by the tests.

**Correctness gate (mandatory before accepting the numbers).** The raster cache key
(`raster|path|sig|size|rtl`) has no algorithm version, and both the cached documents and the rendered
`preview_v2.mp4` were produced by the old code — so the optimisation had to be proven identical:

- `tests/test_mask_path_equiv.py` — 5 tests, reference vs optimised, exact path equality (ring, open
  stroke, 6 random blobs, real word mask with Guo–Hall thinning, real photo at 1/6 scale): **5/5 pass**.
- `tools/verify_raster_equiv.py` — re-traces the three real ww1 images from scratch and compares to the
  on-disk cached docs: **bit-identical** (819 / 14 / 140 strokes, 39 732 points, including lengths,
  brush, brush profile, jumps, kind, color, meta).
- Result: cold tracing got 15× faster **without changing a single output coordinate**, so the already
  rendered film and every cached asset remain valid.

## 4. Profile after the optimisation

```
3956192 function calls … 8.558 s total          (after)
  3.876 s  generate_mask_path
  2.756 s  ├─ _find_start_point      (still per-component np.nonzero; next candidate for vectorisation)
  1.422 s  │   └─ thin()             = 16.6 % of the trace  (1.379 s _guo_hall_iteration)
  0.923 s  ├─ _trace_from_point
  0.606 s  └─ _find_near_point
```

`_count_neighbours` no longer appears. Thinning — which used to be 1.3 % of the pipeline — is now the
second-largest block (16.6 %): that is the *intentional* cost of Guo–Hall (connectivity) and it is now a
reasonable share of a 15× smaller total.

## 5. Thinning choice: cost vs connectivity

| mask | ZS time / components | GH time / components |
|---|---|---|
| ring 5 px (2 104 px) | 0.0042 s / **60** | 0.0053 s / **1** |
| word «الحرب» 190 pt (9 629 px) | 0.1422 s / **152** | 0.2733 s / **1** |

Guo–Hall costs 1.3–1.9× the ZS time on identical masks (≈0.13–0.17 s per word mask at this size) and buys a
single connected skeleton — the root fix for the fragmented look (RC1). On the film's three photos the
thinning portion is `1.42 s / 8.56 s`; the pixel-level cost is negligible next to the walker.

## 6. Caching

- Text/SVG/photo documents are cached by `engine/render/director.py::_cached_doc` under
  `engine/strokes/model.py::stroke_cache_path(key)`; keys: `text|…`, `svg|…`, `raster|path|sig|size|rtl`.
- Cache statistics are exposed (`CACHE_STATS` in `director.py`) and reported by the scene benchmark:
  cold run 13 misses / 0 hits, warm run 13 hits / 0 misses (**hit rate 1.0**).
- Second render of the same film therefore does no tracing/skeletonisation work: 3.08 s scene prep +
  90.9 s render = the earlier warm-cache wall clock for `preview_v2.mp4`; the final render after the
  sub-label change took 173.0 s (it had to recompute the changed timeline label documents).
- `stroke_cache_path` keeps its key scheme deliberately unchanged: a version bump would silently orphan
  every cached document (and the film's provenance), which is why the optimisation was validated against
  the cache instead of renaming the keys.

## 7. Honest notes

1. The `before` figures for `raster_to_strokes`/`cProfile`/cold scene prep were measured with the
   pre-optimisation code on the same machine (Intel i5-1135G7, 15.7 GB RAM, Windows 11) with the same
   inputs; the cold scene-prep run uses an empty temporary cache directory, the warm run the real cache.
2. Single-run timings, no repetition: differences of a few percent are noise, the reported speed-ups are
   13–15× and not sensitive to that.
3. The per-element text build is *not* faster than before on some elements (e.g. s1-title 2.29 s → 3.08 s):
   the word-union pipeline traces longer connected skeletons and Guo–Hall is slower than ZS. It buys
   correctness (fewer pieces, no fragmentation), runs once per element thanks to the cache, and is absorbed
   by the 21.5 fps render loop.
4. `_find_start_point` (2.76 s) remains a per-component Python-level scan; it is the next optimisation
   candidate but was left untouched to keep this phase's change provably output-identical.
