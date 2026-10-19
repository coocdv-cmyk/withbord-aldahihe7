"""توليد تعليق صوتي تجريبي (Windows SAPI) — fixture لإثبات مسار الصوت كاملًا.

ملاحظة صدق: الأصوات المثبتة على الجهاز إنجليزية فقط (David/Zira)؛ هذا الملف
لإثبات الأنبوب (استيراد→فحص→محاذاة→توقيت→مزج→تحقق) وليس عرضًا للصوت العربي.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "qa"

script = (QA / "gate_script_en.txt").read_text(encoding="utf-8")
out = QA / "gate_narration_en.wav"

ps = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.SelectVoice('Microsoft Zira Desktop'); "
    "$s.Rate = 0; "
    f"$s.SetOutputToWaveFile('{out}'); "
    "$s.Speak('" + script.replace("\n\n", " ").replace("\n", " ").replace("'", "''") + "'); "
    "$s.Dispose();"
)
r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
if r.returncode != 0:
    print("فشل TTS:", r.stderr[-500:])
    sys.exit(1)
print("✔ WAV:", out, out.stat().st_size, "بايت")
