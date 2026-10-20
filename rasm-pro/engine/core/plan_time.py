"""Absolute scene boundaries for a plan — one rational timebase for every consumer.

The renderer, the validator and the tests all need the same answer to the
question "which frames belong to scene N?".  This module is the single place
where that answer is calculated.

Priority of timing sources (highest first):

1. absolute audio samples (``start_sample``/``end_sample``) mapped once;
2. absolute plan frames (``start_frame``/``end_frame``);
3. per-scene ``duration_frames`` (legacy plans, accumulated once);
4. fractional seconds in ``duration`` (legacy plans, accumulated exactly).

The conversion is made at the cumulative boundaries, never per scene, so
rounding cannot drift over a long episode.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any

from .timebase import (
    FrameRate,
    SampleRate,
    TimebaseError,
    coerce_frame_rate,
    map_boundaries_to_frames,
)

__all__ = [
    "DEFAULT_FPS",
    "plan_frame_rate",
    "scene_frame_bounds",
]

DEFAULT_FPS = FrameRate(24)


def plan_frame_rate(plan: dict) -> FrameRate:
    """Return the plan's rational frame rate (default 24 when absent)."""
    if not isinstance(plan, dict):
        raise TimebaseError("الخطة يجب أن تكون كائنًا JSON")
    raw = plan.get("fps")
    return DEFAULT_FPS if raw is None else coerce_frame_rate(raw)


def _audio_settings(plan: dict) -> tuple[int, int | None]:
    audio = plan.get("audio") or {}
    if not isinstance(audio, dict):
        raise TimebaseError("audio في الخطة يجب أن يكون كائنًا")
    sr = int(audio.get("sample_rate") or 0)
    total = int(audio.get("total_samples") or 0) or None
    return sr, total


def _scene_sample_bounds(scenes: list[dict]) -> tuple[list[int], list[int], int | None]:
    has = [s.get("start_sample") is not None or s.get("end_sample") is not None for s in scenes]
    if not any(has):
        return [], [], None
    if not all(has):
        raise TimebaseError("بعض المشاهد لها عينات صوتية وبعضها بلا حدود — عقد زمن مختلط")
    starts: list[int] = []
    ends: list[int] = []
    for i, scene in enumerate(scenes, 1):
        try:
            start = int(scene["start_sample"])
            end = int(scene["end_sample"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TimebaseError(f"حدود عينات غير صالحة في المشهد {i}") from exc
        if start < 0 or end < 0:
            raise TimebaseError(f"حدود عينات سالبة في المشهد {i}")
        if end <= start:
            raise TimebaseError(f"مدة عينات غير موجبة في المشهد {i}: [{start}, {end})")
        starts.append(start)
        ends.append(end)
    for i in range(len(scenes) - 1):
        if ends[i] != starts[i + 1]:
            raise TimebaseError(
                f"حدود العينات غير متصلة بين المشهدين {i + 1} و{i + 2}: "
                f"{ends[i]} → {starts[i + 1]}"
            )
    if starts[0] != 0:
        raise TimebaseError(f"المشهد الأول لا يبدأ من العينة 0 (بدأ من {starts[0]})")
    return starts, ends, None


def _scene_plan_frame_bounds(scenes: list[dict]) -> tuple[list[int], list[int]] | None:
    has = [s.get("start_frame") is not None or s.get("end_frame") is not None for s in scenes]
    if not any(has):
        return None
    if not all(has):
        raise TimebaseError("بعض المشاهد لها إطارات مطلقة وبعضها بلا حدود — عقد زمن مختلط")
    starts: list[int] = []
    ends: list[int] = []
    for i, scene in enumerate(scenes, 1):
        try:
            start = int(scene["start_frame"])
            end = int(scene["end_frame"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TimebaseError(f"حدود إطارات غير صالحة في المشهد {i}") from exc
        if start < 0 or end < 0:
            raise TimebaseError(f"حدود إطارات سالبة في المشهد {i}")
        if end <= start:
            raise TimebaseError(f"مدة إطارات غير موجبة في المشهد {i}: [{start}, {end})")
        starts.append(start)
        ends.append(end)
    for i in range(len(scenes) - 1):
        if ends[i] != starts[i + 1]:
            raise TimebaseError(
                f"حدود الإطارات غير متصلة بين المشهدين {i + 1} و{i + 2}: "
                f"{ends[i]} → {starts[i + 1]}"
            )
    if starts[0] != 0:
        raise TimebaseError(f"المشهد الأول لا يبدأ من الإطار 0 (بدأ من {starts[0]})")
    return starts, ends


def _scene_duration_frame_bounds(scenes: list[dict]) -> tuple[list[int], list[int]]:
    acc = 0
    starts: list[int] = []
    ends: list[int] = []
    for i, scene in enumerate(scenes, 1):
        raw = scene.get("duration_frames")
        if isinstance(raw, bool):
            raise TimebaseError(f"duration_frames غير صالح في المشهد {i}")
        try:
            n = int(raw)
        except (TypeError, ValueError) as exc:
            raise TimebaseError(f"duration_frames غير صالح في المشهد {i}") from exc
        if n <= 0 or float(raw) != n:
            raise TimebaseError(f"duration_frames يجب أن يكون عددًا صحيحًا موجبًا (المشهد {i})")
        starts.append(acc)
        acc += n
        ends.append(acc)
    return starts, ends


def _scene_second_bounds(scenes: list[dict], rate: FrameRate) -> tuple[list[int], list[int]]:
    acc = Fraction(0)
    starts: list[int] = []
    ends: list[int] = []
    for i, scene in enumerate(scenes, 1):
        raw = scene.get("duration")
        if raw is None:
            raise TimebaseError(f"المشهد {i} بلا زمن (duration أو عينات أو إطارات)")
        try:
            dur = Fraction(str(raw))
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise TimebaseError(f"duration غير صالح في المشهد {i}: {raw!r}") from exc
        if dur <= 0:
            raise TimebaseError(f"duration يجب أن يكون موجبًا في المشهد {i}")
        starts.append(rate.frame_of_time(acc, mode="round"))
        acc += dur
        ends.append(rate.frame_of_time(acc, mode="round"))
    for i, (start, end) in enumerate(zip(starts, ends), 1):
        if end <= start:
            raise TimebaseError(
                f"المشهد {i} أقصر من إطار واحد عند {rate} — زد المدة أو غيّر معدل الإطارات"
            )
    return starts, ends


def scene_frame_bounds(
    plan: dict,
    *,
    max_seconds: float | None = None,
    scene_range: tuple[int, int] | None = None,
) -> list[dict]:
    """Return absolute frame intervals for the plan's scenes.

    Each result is ``{index, scene, start_frame, end_frame, frames}`` where
    ``index`` is the one-based position in the original plan.  ``scene_range``
    filters the result but does not rebase the frame numbers; callers that emit
    a partial video can subtract the first selected frame when they need an
    output-relative position.
    """
    if not isinstance(plan, dict):
        raise TimebaseError("الخطة يجب أن تكون كائنًا JSON")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise TimebaseError("الخطة بلا مشاهد")
    if any(not isinstance(s, dict) for s in scenes):
        raise TimebaseError("كل مشهد يجب أن يكون كائنًا JSON")

    rate = plan_frame_rate(plan)
    sr, total_samples = _audio_settings(plan)

    sample_starts, sample_ends, _ = _scene_sample_bounds(scenes)
    if sample_starts:
        if sr <= 0:
            raise TimebaseError("الخطة تحمل عينات صوتية لكن audio.sample_rate غير معلن")
        bounds = map_boundaries_to_frames(
            [sample_starts[0], *sample_ends],
            SampleRate(sr),
            rate,
            total_samples=total_samples,
            mode="round",
        )
        starts_f, ends_f = bounds[:-1], bounds[1:]
        if total_samples is not None and sample_ends[-1] != total_samples:
            raise TimebaseError(
                "المشاهد لا تغطي كامل الصوت: "
                f"آخر عينة {sample_ends[-1]} من {total_samples}"
            )
    else:
        frame_bounds = _scene_plan_frame_bounds(scenes)
        if frame_bounds is not None:
            starts_f, ends_f = frame_bounds
            # duration_frames is redundant when absolute frames exist; if it is
            # present it must agree instead of silently overriding the contract.
            for i, scene in enumerate(scenes, 1):
                df = scene.get("duration_frames")
                if df is not None and int(df) != ends_f[i - 1] - starts_f[i - 1]:
                    raise TimebaseError(
                        f"duration_frames لا يطابق حدّي الإطارات في المشهد {i}: "
                        f"{df} != {ends_f[i - 1] - starts_f[i - 1]}"
                    )
        elif all(s.get("duration_frames") is not None for s in scenes):
            starts_f, ends_f = _scene_duration_frame_bounds(scenes)
        else:
            starts_f, ends_f = _scene_second_bounds(scenes, rate)

    max_frame = None
    if max_seconds is not None and max_seconds > 0:
        max_frame = rate.frame_of_time(Fraction(str(max_seconds)), mode="ceil")

    out: list[dict] = []
    for i, scene in enumerate(scenes, 1):
        source_start, source_end = int(starts_f[i - 1]), int(ends_f[i - 1])
        start, end = source_start, source_end
        if max_frame is not None:
            if start >= max_frame:
                break
            end = min(end, max_frame)
        if end <= start:
            continue
        if scene_range and not (int(scene_range[0]) <= i <= int(scene_range[1])):
            continue
        out.append(
            {
                "index": i,
                "scene": scene,
                "start_frame": start,
                "end_frame": end,
                "frames": end - start,
                # Original scene extent before a preview/max-seconds clip. The
                # director uses this for drawing speed so a 10s preview is the
                # first 10s of the full scene, not the scene compressed into 10s.
                "source_start_frame": source_start,
                "source_end_frame": source_end,
                "source_frames": source_end - source_start,
            }
        )
    return out
