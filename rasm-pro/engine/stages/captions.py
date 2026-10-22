"""ترجمة وتوقيت: ملف SRT + ورقة مزامنة — لتسجيل صوتيك على الفيديو.

الفيديو يُسلَّم **بلا سرد** (المؤثرات فقط)، والمسجِّل يحتاج أن يعرف
متى يقول كل سطر.  هذا الملف يبني:

* ``SRT``: التوقيتات measured (من حدود المشاهد) + نص كل مشهد.
* ``CSV`` (ورقة المزامنة): رقم المشهد · الدور · البداية · النهاية · الكلمات · النص.

الزمن: إن وُجدت محاذاة (align.json) فالمصدر حدود العيّنات المقيسة، وإلا
فمدد الخطة التقديرية — ويقال أيّهما استُخدم.
"""
from __future__ import annotations

from typing import Any


def _fmt(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds - hours * 3600 - minutes * 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace(".", ",")


def scene_timings(plan: dict, alignment: dict | None = None) -> list[dict]:
    """توقيت كل مشهد: (start, end, source)."""
    scenes = (plan or {}).get("scenes") or []
    out: list[dict] = []
    segments = []
    if alignment:
        segments = list(alignment.get("segments") or [])
    for index, scene in enumerate(scenes):
        start = end = None
        source = "plan"
        if index < len(segments):
            seg = segments[index]
            try:
                rate = float((alignment or {}).get("sample_rate") or 48000)
                start = float(seg["start_sample"]) / rate
                end = float(seg["end_sample"]) / rate
                source = "alignment"
            except Exception:
                start = end = None
        if start is None or end is None:
            try:
                start = float(scene.get("start_frame") or 0) / 24.0
                end = float(scene.get("end_frame") or 0) / 24.0
            except Exception:
                start = end = 0.0
            source = "plan"
        out.append(
            {
                "id": scene.get("id", index + 1),
                "role": scene.get("role") or "",
                "start": float(start),
                "end": float(end),
                "source": source,
                "text": str(scene.get("narration") or "").strip(),
            }
        )
    return out


def build_srt(plan: dict, alignment: dict | None = None) -> str:
    """ملف SRT (توقيت + نص) كما تستهلكه برامج المونتاج."""
    lines: list[str] = []
    for index, item in enumerate(scene_timings(plan, alignment), 1):
        lines.append(str(index))
        lines.append(f"{_fmt(item['start'])} --> {_fmt(item['end'])}")
        lines.append(item["text"] or "")
        lines.append("")
    return "\n".join(lines)


def build_sync_csv(plan: dict, alignment: dict | None = None) -> str:
    """ورقة المزامنة: ماذا يُقال ومتى."""
    rows = ["scene,role,start_sec,end_sec,words,source,text"]
    for item in scene_timings(plan, alignment):
        text = item["text"].replace('"', '""')
        rows.append(
            '{id},{role},{start:.3f},{end:.3f},{words},"{text}",{source}'.format(
                id=item["id"],
                role=item["role"],
                start=item["start"],
                end=item["end"],
                words=len(item["text"].split()),
                text=text,
                source=item["source"],
            )
        )
    return "\n".join(rows)


def narration_lines(plan: dict, alignment: dict | None = None) -> list[str]:
    """نص كل مشهد مرتّبًا (ورقة قراءة للمسجِّل)."""
    return [item["text"] for item in scene_timings(plan, alignment) if item["text"]]
