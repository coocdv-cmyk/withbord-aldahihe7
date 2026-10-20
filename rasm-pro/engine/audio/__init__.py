"""طبقة الصوت: فحص، استيراد تعليق صوتي، قياس جهارة، محاذاة مقيسة، تحقق من التصدير."""
from .align import (
    ALIGN_VERSION,
    Alignment,
    AlignmentError,
    SpeechSegment,
    alignment_frames,
    baseline_align,
    detect_speech,
    load_alignment,
    measured_align,
    save_alignment,
)
from .gate import NarrationGate, evaluate_narration_gate
from .loudness import (
    LoudnessError,
    LoudnessReport,
    TARGETS,
    measure_loudness,
    measure_samples,
)
from .narration import (
    import_narration,
    load_narration,
    measure_project_narration,
    normalize_narration,
    resolve_narration,
)
from .probe import AudioError, ffprobe_path, probe_audio, sha256_file
from .sfx import SfxLibrary, build_track, mux_into

__all__ = [
    "ALIGN_VERSION",
    "Alignment",
    "AlignmentError",
    "AudioError",
    "LoudnessError",
    "LoudnessReport",
    "NarrationGate",
    "SfxLibrary",
    "SpeechSegment",
    "TARGETS",
    "alignment_frames",
    "baseline_align",
    "build_track",
    "detect_speech",
    "evaluate_narration_gate",
    "ffprobe_path",
    "import_narration",
    "load_alignment",
    "load_narration",
    "measure_loudness",
    "measure_project_narration",
    "measure_samples",
    "measured_align",
    "mux_into",
    "normalize_narration",
    "probe_audio",
    "resolve_narration",
    "save_alignment",
    "sha256_file",
]
