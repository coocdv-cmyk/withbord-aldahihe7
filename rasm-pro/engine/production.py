"""One production contract for the CLI and Studio.

The renderer is only one part of a deliverable.  A final video is allowed to
exist only when all of these are true, measured rather than assumed:

* the approval gate is open for every asset the plan uses;
* the narration file on disk still matches the manifest (SHA-256, sample count,
  sample rate) and the loudness gate;
* the alignment still describes the active plan's scenes and covers the exact
  audio file;
* the SFX library is complete and the mix is written;
* every scene fits its time and every required element can be read;
* the written file passes FFprobe (size, rate, frames, duration, audio).

``prepare_production`` performs every check before a writer is opened.
``render_prepared`` renders and ``finalize_production`` builds the SFX mix and
verifies the file.  Both the CLI (``rasm render``) and the Studio bridge call
these functions, so the two paths cannot drift apart again.
"""
from __future__ import annotations

import json

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from .audio.align import Alignment, load_alignment
from .audio.gate import evaluate_narration_gate
from .audio.loudness import TARGETS
from .audio.narration import load_narration, resolve_narration
from .audio.probe import probe_audio
from .audio.sfx import build_track, library_status, mux_into
from .core.assets import ApprovalError, evaluate_gate
from .core.log import get_logger
from .core.project import read_manifest
from .core.timebase import frame_rate_json
from .core.util import write_json
from .render import Director
from .render.director import RenderPreflightError
from .render.validate import validate_video

log = get_logger("production")

__all__ = [
    "ProductionError",
    "ProductionPreflight",
    "ProductionResult",
    "prepare_production",
    "render_prepared",
    "finalize_production",
    "render_production",
]


class ProductionError(RuntimeError):
    """A final production was refused (after the checks, before/after render)."""

    def __init__(self, report: dict):
        self.report = report
        items = report.get("blocking") or []
        detail = "; ".join(
            f"{b.get('reason', 'unknown')}: {b.get('detail', '')}" for b in items[:12]
        )
        super().__init__("الإنتاج مرفوض — " + (detail or "سبب غير معلن"))


def _compact_audio(info: dict | None) -> dict:
    if not info:
        return {}
    keys = (
        "file",
        "path",
        "bytes",
        "sha256",
        "codec",
        "sample_rate",
        "channels",
        "duration",
        "duration_sec",
        "duration_exact",
        "total_samples",
        "deep",
    )
    return {k: info.get(k) for k in keys if k in info}


def _same_text(left: Any, right: Any) -> bool:
    return " ".join(str(left or "").split()) == " ".join(str(right or "").split())


def _alignment_report(
    project_dir: Path,
    plan: dict,
    expected_samples: int | None,
) -> tuple[dict, list[dict], list[dict]]:
    """Validate that the stored alignment still describes this plan/audio."""
    report: dict = {
        "ok": False,
        "path": str(project_dir / "audio" / "alignment.json"),
        "level": None,
        "method": None,
        "segments": 0,
        "total_samples": None,
        "reasons": [],
    }
    blocking: list[dict] = []
    warnings: list[dict] = []
    al: Alignment | None = load_alignment(project_dir)
    if al is None:
        report["reasons"].append("alignment-missing")
        blocking.append(
            {
                "reason": "alignment-missing",
                "detail": "لا توجد محاذاة مقيسة — لا يمكن ضمان أن السرد يطابق المشاهد.",
                "source": "alignment",
            }
        )
        return report, blocking, warnings

    scenes = [s for s in plan.get("scenes") or [] if isinstance(s, dict)]
    report.update(
        {
            "level": al.level,
            "method": al.method,
            "segments": len(al.segments),
            "total_samples": al.total_samples,
        }
    )
    reasons: list[str] = []
    if len(al.segments) != len(scenes):
        reasons.append("segment-count")
    for index, (scene, seg) in enumerate(zip(scenes, al.segments)):
        try:
            same_id = int(scene.get("id")) == int(seg.scene_id)
        except (TypeError, ValueError):
            same_id = str(scene.get("id")) == str(seg.scene_id)
        if not same_id or not _same_text(scene.get("narration"), seg.text):
            reasons.append(f"text-or-id@{index}")
    if expected_samples is not None and int(al.total_samples) != int(expected_samples):
        reasons.append("total-samples")
    if al.segments:
        starts = [int(s.start_sample) for s in al.segments]
        ends = [int(s.end_sample) for s in al.segments]
        contiguous = (
            starts[0] == 0
            and all(end == next_start for end, next_start in zip(ends, starts[1:]))
            and ends[-1] == int(al.total_samples)
            and all(end > start for start, end in zip(starts, ends))
        )
        if not contiguous:
            reasons.append("not-contiguous")
    else:
        reasons.append("empty")
    if reasons:
        report["reasons"] = sorted(set(reasons))
        blocking.append(
            {
                "reason": "alignment-stale",
                "detail": "المحاذاة لا تطابق الخطة/الصوت الحالي: " + ", ".join(report["reasons"]),
                "source": "alignment",
            }
        )
    else:
        report["ok"] = True
    return report, blocking, warnings


@dataclass
class ProductionPreflight:
    mode: str
    ok: bool
    project_dir: Path
    plan: dict
    plan_path: Path | None = None
    size: tuple[int, int] = (1280, 720)
    scene_range: tuple[int, int] | None = None
    max_seconds: float | None = None
    resumable: bool = True
    narration_for_mux: Path | None = None
    sfx_enabled: bool = True
    sfx_preset: str = "paper"
    silent: bool = False
    audio_file: Path | None = None
    audio: dict = field(default_factory=dict)
    alignment: dict = field(default_factory=dict)
    sfx_library: dict = field(default_factory=dict)
    director_preflight: dict | None = None
    gates: dict = field(default_factory=dict)
    blocking: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    director: Director | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "ok": self.ok,
            "project_dir": str(self.project_dir),
            "plan_path": str(self.plan_path) if self.plan_path else None,
            "size": list(self.size),
            "scene_range": list(self.scene_range) if self.scene_range else None,
            "max_seconds": self.max_seconds,
            "sfx_enabled": self.sfx_enabled,
            "sfx_preset": self.sfx_preset,
            "audio_file": str(self.audio_file) if self.audio_file else None,
            "audio": self.audio,
            "alignment": self.alignment,
            "sfx_library": self.sfx_library,
            "director_preflight": self.director_preflight,
            "gates": self.gates,
            "blocking": self.blocking,
            "warnings": self.warnings,
        }


@dataclass
class ProductionResult:
    mode: str
    ok: bool
    blocking: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    mix: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    mix_report: str | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "ok": self.ok,
            "blocking": self.blocking,
            "warnings": self.warnings,
            "mix": self.mix,
            "validation": self.validation,
            "mix_report": self.mix_report,
        }


def _add(
    blocking: list[dict],
    warnings: list[dict],
    mode: str,
    reason: str,
    detail: str,
    **extra: Any,
) -> None:
    item = {**extra, "reason": reason, "detail": detail}
    if mode == "final":
        blocking.append(item)
    else:
        item["severity"] = "preview-only"
        warnings.append(item)


def prepare_production(
    project_dir: str | Path,
    plan: dict,
    *,
    plan_path: str | Path | None = None,
    manifest: dict | None = None,
    mode: str = "final",
    size: tuple[int, int] = (1280, 720),
    fps: Any = None,
    audio: str | Path | None = None,
    max_seconds: float | None = None,
    scene_range: tuple[int, int] | None = None,
    sfx: bool = True,
    sfx_preset: str = "paper",
    crf: int = 19,
    target_lufs: float | None = TARGETS["video"],
    silent: bool = False,
    resumable: bool = True,
) -> ProductionPreflight:
    """Run every production check before creating an output file.

    ``silent=True`` delivers the episode **without a voice track** (the effects
    only): the picture carries the argument, and the human voice is laid over
    it in the edit.  The narration is then not part of the contract at all —
    no narration gate, no alignment gate, and the mix is the effects alone.
    """
    pd = Path(project_dir).resolve()
    mode = str(mode or "final").strip().lower()
    if mode not in ("final", "preview"):
        raise ValueError(f"وضع غير معروف: {mode!r}")
    prep = ProductionPreflight(
        mode=mode,
        ok=True,
        silent=bool(silent),
        resumable=bool(resumable),
        project_dir=pd,
        plan=plan,
        plan_path=Path(plan_path).resolve() if plan_path else None,
        size=(int(size[0]), int(size[1])),
        scene_range=scene_range,
        max_seconds=max_seconds,
        sfx_enabled=bool(sfx),
        sfx_preset=str(sfx_preset),
    )
    blocking: list[dict] = []
    warnings: list[dict] = []

    if manifest is None:
        try:
            manifest = read_manifest(pd)
        except Exception as exc:
            _add(blocking, warnings, mode, "manifest-unreadable", str(exc), source="project")
            manifest = None
    if manifest is None:
        warnings.append(
            {
                "reason": "manifest-missing",
                "detail": "لا يوجد project.json — لا يمكن فحص سلسلة الاعتماد.",
                "source": "project",
            }
        )

    # --- assets ---------------------------------------------------------
    if manifest is not None:
        try:
            gate = evaluate_gate(plan, pd, manifest=manifest, mode=mode)
            prep.gates["assets"] = {
                "ok": gate.ok,
                "used": len(gate.used),
                "blocking": len(gate.blocking),
                "warnings": len(gate.warnings),
            }
            for item in gate.blocking:
                blocking.append(
                    {
                        "reason": item.get("reason"),
                        "detail": item.get("detail") or "",
                        "path": item.get("path"),
                        "display": item.get("display"),
                        "source": "asset-gate",
                    }
                )
            warnings.extend(
                {
                    "reason": item.get("reason"),
                    "detail": item.get("detail") or "",
                    "path": item.get("path"),
                    "display": item.get("display"),
                    "source": "asset-gate",
                }
                for item in gate.warnings
            )
        except ApprovalError as exc:
            blocking.append({"reason": "asset-gate-error", "detail": str(exc), "source": "asset-gate"})

    # --- narration manifest and the actual bytes on disk ----------------
    narration = load_narration(pd)
    plan_audio = plan.get("audio") or {}
    declared_audio = bool(plan_audio.get("file")) if isinstance(plan_audio, dict) else False
    candidate: Path | None = None
    if silent:
        # a silent deliverable: the picture carries the argument and the human
        # voice is laid over it in the edit — no narration is part of the deal.
        candidate = None
    elif audio:
        candidate = Path(audio)
        if not candidate.is_absolute():
            candidate = pd / candidate
    elif declared_audio:
        candidate = Path(str(plan_audio["file"]))
        if not candidate.is_absolute():
            candidate = pd / candidate
    elif narration is not None:
        candidate = resolve_narration(pd, narration)

    actual_audio: dict | None = None
    if candidate is not None:
        candidate = candidate.resolve()
        if not candidate.exists():
            _add(
                blocking,
                warnings,
                mode,
                "narration-file-missing",
                f"ملف السرد غير موجود: {candidate}",
                source="audio",
            )
        else:
            try:
                actual_audio = probe_audio(candidate, deep=True)
            except Exception as exc:
                _add(
                    blocking,
                    warnings,
                    mode,
                    "narration-unreadable",
                    f"تعذّر فحص ملف السرد: {exc}",
                    source="audio",
                )
        if actual_audio is not None:
            prep.audio_file = candidate
            actual_sha = str(actual_audio.get("sha256") or "")
            manifest_sha = str((narration or {}).get("sha256") or "")
            actual_samples = int(actual_audio.get("total_samples") or 0)
            manifest_samples = int((narration or {}).get("total_samples") or 0)
            prep.audio = {
                "path": str(candidate),
                "actual_sha256": actual_sha,
                "manifest_sha256": manifest_sha,
                "actual_total_samples": actual_samples,
                "manifest_total_samples": manifest_samples,
                "sample_rate": actual_audio.get("sample_rate"),
                "duration_sec": actual_audio.get("duration_sec"),
                "duration_exact": actual_audio.get("duration_exact"),
                "codec": actual_audio.get("codec"),
                "deep": bool(actual_audio.get("deep")),
            }
            if narration is None:
                _add(
                    blocking,
                    warnings,
                    mode,
                    "narration-not-registered",
                    "الملف الصوتي غير مسجّل في audio/narration.json — استورده بـ rasm audio.",
                    source="audio",
                )
            else:
                if not manifest_sha:
                    _add(
                        blocking,
                        warnings,
                        mode,
                        "narration-hash-missing",
                        "الوصف لا يحمل بصمة SHA-256 للملف المستخدم.",
                        source="audio",
                    )
                elif actual_sha != manifest_sha:
                    _add(
                        blocking,
                        warnings,
                        mode,
                        "narration-hash-mismatch",
                        f"بصمة الملف {actual_sha[:12]}… لا تطابق الوصف {manifest_sha[:12]}…",
                        source="audio",
                    )
                if manifest_samples and actual_samples != manifest_samples:
                    _add(
                        blocking,
                        warnings,
                        mode,
                        "narration-metadata-stale",
                        f"عدد العينات الفعلي {actual_samples} لا يطابق الوصف {manifest_samples}.",
                        source="audio",
                    )
                manifest_rate = int((narration or {}).get("sample_rate") or 0)
                if manifest_rate and int(actual_audio.get("sample_rate") or 0) != manifest_rate:
                    _add(
                        blocking,
                        warnings,
                        mode,
                        "narration-metadata-stale",
                        "معدل العينات الفعلي لا يطابق الوصف.",
                        source="audio",
                    )
                declared_sha = str((plan_audio or {}).get("sha256") or "")
                if declared_sha and declared_sha != actual_sha:
                    _add(
                        blocking,
                        warnings,
                        mode,
                        "plan-audio-stale",
                        "الخطة بُنيت على ملف صوتي آخر — أعد بناء الخطة بعد استيراد السرد الحالي.",
                        source="audio",
                    )

        if narration is not None and not silent:
            try:
                gate = evaluate_narration_gate(
                    pd, plan, mode=mode, target_lufs=target_lufs
                )
                prep.gates["narration"] = gate.to_dict()
                blocking.extend(
                    {**item, "source": "narration-gate"} for item in gate.blocking
                )
                warnings.extend(
                    {**item, "source": "narration-gate"} for item in gate.warnings
                )
            except Exception as exc:
                _add(
                    blocking,
                    warnings,
                    mode,
                    "narration-gate-error",
                    str(exc),
                    source="narration-gate",
                )

    if (narration is not None or declared_audio) and not silent:
        al_report, al_blocking, al_warnings = _alignment_report(
            pd,
            plan,
            int((actual_audio or {}).get("total_samples") or (narration or {}).get("total_samples") or 0)
            or None,
        )
        prep.alignment = al_report
        if mode == "preview":
            for item in al_blocking:
                warnings.append({**item, "severity": "preview-only"})
        else:
            blocking.extend(al_blocking)
        warnings.extend(al_warnings)

    # --- SFX library ----------------------------------------------------
    if sfx:
        try:
            prep.sfx_library = library_status()
        except Exception as exc:
            _add(
                blocking,
                warnings,
                mode,
                "sfx-library-error",
                str(exc),
                source="sfx",
            )
        else:
            if not prep.sfx_library.get("complete"):
                _add(
                    blocking,
                    warnings,
                    mode,
                    "sfx-library-incomplete",
                    "تسجيلات المؤثرات مفقودة: "
                    + ", ".join(prep.sfx_library.get("missing") or []),
                    source="sfx",
                )

    # --- renderer preflight (fit + required elements) -------------------
    try:
        prep.director = Director(
            plan,
            canvas=tuple(plan.get("canvas") or [2560, 1440]),
            out_size=prep.size,
            fps=fps,
            crf=crf,
            project_dir=pd,
        )
    except Exception as exc:
        _add(
            blocking,
            warnings,
            mode,
            "director-error",
            str(exc),
            source="render",
        )
    else:
        try:
            report = prep.director.preflight(
                scene_range=scene_range, max_seconds=max_seconds
            )
        except Exception as exc:
            _add(
                blocking,
                warnings,
                mode,
                "preflight-error",
                str(exc),
                source="render",
            )
        else:
            prep.director_preflight = report
            if not report.get("ok"):
                if mode == "final":
                    blocking.extend(
                        {**item, "source": "render-preflight"}
                        for item in report.get("blocking") or []
                    )
                else:
                    warnings.extend(
                        {**item, "source": "render-preflight", "severity": "preview-only"}
                        for item in report.get("blocking") or []
                    )
            warnings.extend(
                {**item, "source": "render-preflight"}
                for item in report.get("warnings") or []
            )

    # --- a ranged export cannot outrun the narration --------------------
    if (
        prep.audio_file
        and prep.audio
        and scene_range
        and prep.director is not None
    ):
        try:
            bounds = prep.director.scene_bounds(
                scene_range=scene_range, max_seconds=max_seconds
            )
            start = float(bounds[0]["start_frame"]) / prep.director.fps
            length = sum(int(b["frames"]) for b in bounds) / prep.director.fps
            audio_duration = float(prep.audio.get("duration_sec") or 0.0)
            if audio_duration and start + length > audio_duration + 0.05:
                _add(
                    blocking,
                    warnings,
                    mode,
                    "scene-range-exceeds-narration",
                    f"النطاق يبدأ عند {start:.2f}ث ويمتد {length:.2f}ث داخل سرد مدته {audio_duration:.2f}ث.",
                    source="audio",
                )
        except Exception:
            pass

    prep.blocking = blocking
    prep.warnings = warnings
    prep.ok = not blocking
    return prep


def _raise_if_refused(prep: ProductionPreflight) -> None:
    if prep.ok:
        return
    if prep.director_preflight is not None and not prep.director_preflight.get("ok"):
        raise RenderPreflightError(prep.director_preflight)
    raise ProductionError(prep.to_dict())


def finalize_production(
    prep: ProductionPreflight,
    result: dict,
    out_path: str | Path,
) -> ProductionResult:
    """Build/mux SFX and verify the written file against the contract."""
    out = Path(out_path)
    report = ProductionResult(mode=prep.mode, ok=True)
    muxed = False
    if prep.sfx_enabled:
        sfx_json = result.get("sfx")
        if sfx_json and Path(sfx_json).exists():
            try:
                wav = Path(str(out)).with_suffix(".sfx.wav")
    # the mix: the effects alone in a silent deliverable, under the voice when
    # there is one (the ducking follows the real narration)
                info = build_track(
                    sfx_json,
                    wav,
                    preset=prep.sfx_preset,
                    duration=float(result.get("seconds") or 0.0),
                    narration=None if prep.silent else prep.audio_file,
                )
                mux = mux_into(
                    out,
                    wav,
                    out,
                    narration=prep.narration_for_mux,
                    duration=float(result.get("seconds") or 0.0),
                )
                report.mix = {**info, "mux": mux, "mode": mux.get("mode")}
                report.mix_report = str(Path(str(out)).with_suffix(".mix.json"))
                write_json(report.mix_report, report.mix)
                result["sfx_wav"] = str(wav)
                result["audio_mode"] = mux["mode"]
                result["mix_report"] = report.mix_report
                muxed = True
                if info.get("synthetic_fallback"):
                    _add(
                        report.blocking,
                        report.warnings,
                        prep.mode,
                        "sfx-synthetic-fallback",
                        "تسجيلات مؤثرات مفقودة — لا يُنشر بديل توليدي.",
                        source="sfx",
                    )
                if not info.get("counts_by_type"):
                    report.warnings.append(
                        {
                            "reason": "sfx-no-events",
                            "detail": "لا أحداث رسم في هذا المخرج — مسار المؤثرات صامت.",
                            "source": "sfx",
                        }
                    )
            except Exception as exc:
                _add(
                    report.blocking,
                    report.warnings,
                    prep.mode,
                    "sfx-mix-failed",
                    str(exc),
                    source="sfx",
                )
        else:
            report.warnings.append(
                {
                    "reason": "sfx-events-missing",
                    "detail": "لم يُكتب ملف أحداث القلم — لا مؤثرات لهذا المخرج.",
                    "source": "sfx",
                }
            )

    expect_audio = bool(prep.audio_file) or muxed
    try:
        validation = validate_video(
            out,
            expect_size=prep.size,
            expect_fps=result.get("fps"),
            expect_frames=result.get("frames"),
            expect_audio=expect_audio,
            expect_duration_sec=result.get("duration_sec_exact"),
            tolerance_frames=1,
        )
        report.validation = validation
        if not validation.get("ok"):
            _add(
                report.blocking,
                report.warnings,
                prep.mode,
                "output-validation-failed",
                "; ".join(
                    f"{check['check']}: {check['detail']}"
                    for check in validation.get("checks") or []
                    if not check.get("ok")
                ),
                source="validation",
            )
    except Exception as exc:
        report.validation = {"ok": False, "checks": [], "error": str(exc)}
        _add(
            report.blocking,
            report.warnings,
            prep.mode,
            "output-validation-error",
            str(exc),
            source="validation",
        )

    report.ok = not report.blocking
    return report


def render_prepared(
    prep: ProductionPreflight,
    out_path: str | Path,
    *,
    on_progress=None,
) -> dict:
    """Render a prepared production and finalize its audio/verification.

    The render is **resumable** by default: every scene is written as a part
    on disk, so a crash costs one scene instead of the whole episode, and a
    re-run continues where it stopped.  The parts are joined by a stream copy
    (no re-encode), and the voice and the effects are muxed once at the end.
    """
    if prep.mode == "final":
        _raise_if_refused(prep)
    if prep.director is None:
        raise ProductionError(prep.to_dict())
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # the narration is cut to the exported range before it is muxed, so the
    # voice and the picture start together in a scene-range export too
    narration_for_mux: Path | None = None
    if prep.audio_file and prep.scene_range:
        try:
            narration_for_mux = _cut_narration(
                prep.director, prep.audio_file, out, prep.scene_range, prep.max_seconds
            )
        except Exception as exc:
            log.warning("could not cut the narration for the range (%s)", exc)
            narration_for_mux = None
    elif prep.audio_file:
        narration_for_mux = prep.audio_file

    if prep.resumable:
        from .core.util import sha256_text
        from .render.parts import render_resumable
        from .render.video import require_ffmpeg

        bounds = prep.director.scene_bounds(
            scene_range=prep.scene_range, max_seconds=prep.max_seconds
        )
        fingerprint = sha256_text(json.dumps(prep.plan, sort_keys=True, default=str))
        result = render_resumable(
            prep.director,
            out,
            plan_fingerprint=fingerprint,
            scene_bounds=bounds,
            ffmpeg=require_ffmpeg(),
            on_progress=on_progress,
        )
        result["resumable"] = True
        # the pen events of every part are merged into one file next to the
        # joined video ? that is what the sound layer reads
        result["sfx"] = str(out.with_suffix(".sfx.json"))
        # the film duration (not the wall time) is what the contract checks,
        # in the same form the direct render reports it
        frames = int(result.get("frames") or 0)
        if prep.director is not None:
            exact = prep.director.fps_rate.time_of_frames(frames)
        else:
            exact = frames / 24.0
        result["duration_sec_exact"] = str(exact)
        result["seconds"] = round(float(exact), 6)
        result["render_seconds"] = result.get("seconds_wall") or result.get("seconds")
        result.setdefault("fps", frame_rate_json(prep.director.fps_rate) if prep.director else None)
        result.setdefault("audio_start_sec", 0.0)
        result.setdefault("output_start_frame", 0)
        result.setdefault("drift_frames", 0)
    else:
        result = prep.director.render(
            out,
            audio=prep.audio_file,
            max_seconds=prep.max_seconds,
            scene_range=prep.scene_range,
            strict=prep.mode == "final",
            preflight_report=prep.director_preflight,
        )
        result["resumable"] = False
        narration_for_mux = None  # the writer already muxed it
    result["plan_path"] = str(prep.plan_path) if prep.plan_path else None
    result["audio"] = str(prep.audio_file) if prep.audio_file else None
    result["mode"] = prep.mode
    prep.narration_for_mux = narration_for_mux
    final = finalize_production(prep, result, out)
    result["production"] = final.to_dict()
    result["ok"] = final.ok
    if prep.mode == "final" and not final.ok:
        raise ProductionError({"blocking": final.blocking, "warnings": final.warnings})
    return result


def _cut_narration(
    director: Any,
    audio_file: Path,
    out: Path,
    scene_range: tuple[int, int],
    max_seconds: float | None,
) -> Path:
    """Cuts the narration so it starts with the first scene of the range."""
    import subprocess

    from .render.video import require_ffmpeg

    bounds = director.scene_bounds(scene_range=scene_range, max_seconds=max_seconds)
    start = float(bounds[0]["start_frame"]) / float(director.fps)
    length = sum(int(b["frames"]) for b in bounds) / float(director.fps)
    target = out.with_name(out.stem + ".narration-range.wav")
    cmd = [
        require_ffmpeg(), "-y", "-v", "error",
        "-ss", f"{start:.6f}", "-i", str(audio_file),
        "-t", f"{length:.6f}", "-ac", "2", "-ar", "48000",
        "-c:a", "pcm_s16le", str(target),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-200:])
    return target

def render_production(
    project_dir: str | Path,
    plan: dict,
    *,
    out_path: str | Path | None = None,
    plan_path: str | Path | None = None,
    manifest: dict | None = None,
    mode: str = "final",
    size: tuple[int, int] = (1280, 720),
    fps: Any = None,
    audio: str | Path | None = None,
    max_seconds: float | None = None,
    scene_range: tuple[int, int] | None = None,
    sfx: bool = True,
    sfx_preset: str = "paper",
    crf: int = 19,
    target_lufs: float | None = TARGETS["video"],
    resumable: bool = True,
    on_progress=None,
) -> dict:
    """Prepare + render + finalize in one call (the shared production path)."""
    prep = prepare_production(
        project_dir,
        plan,
        plan_path=plan_path,
        manifest=manifest,
        mode=mode,
        size=size,
        fps=fps,
        audio=audio,
        max_seconds=max_seconds,
        scene_range=scene_range,
        sfx=sfx,
        sfx_preset=sfx_preset,
        crf=crf,
        target_lufs=target_lufs,
        resumable=resumable,
    )
    if prep.mode == "final":
        _raise_if_refused(prep)
    if out_path is None:
        pd = Path(project_dir)
        out_path = pd / "render" / (
            "preview.mp4" if prep.mode == "preview" else "episode.mp4"
        )
    return render_prepared(prep, out_path, on_progress=on_progress)
