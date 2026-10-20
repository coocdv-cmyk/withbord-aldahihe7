"""The narration gate — what a production render is allowed to assume about audio.

Rules (all measured, none guessed):

* If the plan declares narration, the project must have one.
* A narration that was never measured is not production-ready (we do not
  publish numbers we did not measure).
* A narration outside the speech window must be normalized on purpose, not
  by accident.
* A narration shorter than the picture fails loudly (never trimmed).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..core.log import get_logger

log = get_logger("audio.gate")

__all__ = ["NarrationGate", "evaluate_narration_gate", "SPEECH_WINDOW_LUFS", "TARGET_TOLERANCE_LU"]

# A spoken narration that lives outside this window is unusable in practice
# (too quiet to hear, or hot enough to distort in the codec).
SPEECH_WINDOW_LUFS = (-30.0, -9.0)
# Distance from the delivery target that still counts as "on target".
TARGET_TOLERANCE_LU = 6.0


@dataclass
class NarrationGate:
    mode: str
    ok: bool
    has_narration: bool = False
    measured: bool = False
    lufs: float | None = None
    target: float | None = None
    duration_sec: float | None = None
    picture_seconds: float | None = None
    blocking: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _plan_seconds(plan: dict | None) -> float | None:
    if not isinstance(plan, dict):
        return None
    stats = plan.get("stats") or {}
    for key in ("duration", "estimated_duration"):
        value = stats.get(key)
        if value:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    total = plan.get("timebase") or {}
    if total.get("end_frame") and plan.get("fps"):
        fps = plan.get("fps")
        num = fps.get("num") if isinstance(fps, dict) else fps
        den = fps.get("den") if isinstance(fps, dict) else 1
        try:
            return float(total["end_frame"]) * float(den or 1) / float(num)
        except Exception:
            return None
    return None


def evaluate_narration_gate(
    project_dir: str | Path,
    plan: dict | None = None,
    *,
    mode: str = "final",
    target_lufs: float | None = None,
) -> NarrationGate:
    """Decide whether the narration may be used in ``mode``."""
    mode = str(mode or "final").strip().lower()
    report = NarrationGate(mode=mode, ok=True)
    pd = Path(project_dir)
    blocking: list[dict] = []

    from .narration import load_narration, resolve_narration

    manifest = load_narration(pd)
    picture = _plan_seconds(plan)
    report.picture_seconds = picture

    plan_audio = (plan or {}).get("audio") or {}
    wants_audio = bool(plan_audio.get("file")) or bool((plan or {}).get("audio"))

    if manifest is None:
        if wants_audio:
            blocking.append(
                {
                    "reason": "narration-missing",
                    "detail": "الخطة تعلن صوتًا والمشروع بلا تعليق صوتي مستورد.",
                }
            )
        else:
            report.warnings.append(
                {"reason": "no-narration", "detail": "لا يوجد تعليق صوتي — الحلقة صامتة."}
            )
        report.blocking = blocking
        report.ok = not blocking or mode != "final"
        if blocking and mode != "final":
            report.warnings.extend(blocking)
            report.blocking = []
        return report

    report.has_narration = True
    loud = manifest.get("loudness")
    if not isinstance(loud, dict) or loud.get("lufs_integrated") is None:
        blocking.append(
            {
                "reason": "narration-not-measured",
                "detail": "الجهارة غير مقيسة — شغّل: rasm audio <project> (يُقاس عند الاستيراد).",
            }
        )
        report.blocking = blocking
        report.ok = not blocking or mode != "final"
        if blocking and mode != "final":
            report.warnings.extend(blocking)
            report.blocking = []
        return report

    report.measured = True
    report.lufs = float(loud.get("lufs_integrated"))
    report.duration_sec = float(loud.get("duration_sec") or 0.0) or None

    low, high = SPEECH_WINDOW_LUFS
    if report.lufs < low or report.lufs > high:
        blocking.append(
            {
                "reason": "narration-outside-speech-window",
                "detail": f"الجهارة {report.lufs:.1f} LUFS خارج النطاق المقبول [{low:.0f}, {high:.0f}].",
            }
        )
    if target_lufs is not None:
        report.target = float(target_lufs)
        if abs(report.lufs - report.target) > TARGET_TOLERANCE_LU:
            blocking.append(
                {
                    "reason": "narration-off-target",
                    "detail": (
                        f"الجهارة {report.lufs:.1f} LUFS تبتعد عن الهدف {report.target:.1f} "
                        f"بأكثر من {TARGET_TOLERANCE_LU:.0f} LU — "
                        "شغّل: rasm audio <project> --normalize "
                        f"{report.target:.0f} (تطبيع صريح ومسجَّل)."
                    ),
                }
            )
    if picture and report.duration_sec and report.duration_sec < picture - 0.05:
        blocking.append(
            {
                "reason": "narration-shorter-than-picture",
                "detail": (
                    f"السرد {report.duration_sec:.2f}ث أقصر من الصورة {picture:.2f}ث — "
                    "لا يُقصّ الصوت: زد مدة التسجيل أو وسّع الخطة."
                ),
            }
        )

    if blocking and mode != "final":
        report.warnings.extend(blocking)
    else:
        report.blocking = blocking
    report.ok = not report.blocking
    return report
