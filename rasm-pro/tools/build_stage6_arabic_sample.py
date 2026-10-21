"""Build the independent Arabic acceptance sample for Stage 6.

This is deliberately a **separate project** (``stage6-arabic-sample``).  It
never reads or writes ``projects/ww1``.  The workflow is the production CLI,
not a shortcut: project manifest -> research assets -> narration import ->
normalization -> measured alignment -> plan rebuild -> asset approval ->
credits -> final render -> verification.

The narration is synthetic (Microsoft Edge TTS, ``ar-EG-ShakirNeural``) and is
documented as such in the evidence report; it is not human production audio.

Requires ``edge-tts`` in the engine virtualenv::

    rasm-pro\\.venv\\Scripts\\python.exe -m pip install edge-tts
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
PROJECT_ID = "stage6-arabic-sample"
PD = ROOT / "projects" / PROJECT_ID
FFMPEG = REPO / "studio" / "runtime" / "ffmpeg.exe"
PY = sys.executable

SCENES = [
    "كم فكرة رائعة نسيناها لأنها بقيت حبيسة ورقة صغيرة، وكم فكرة أخرى لم تجد من يكتبها في وقتها فماتت في الطريق قبل أن يراها أحد، ثم جاء غيرنا وكتبها بعد سنوات؟",
    "الذاكرة لا تحتفظ بكل شيء، لكنها تحتفظ بما نراه وما نلمسه وما نكتبه وما نعيد رسمه بأيدينا كل يوم.",
    "حين نحوّل الفكرة إلى رسم بسيط جدًا، يجد العقل صورة واضحة جدًا يعود إليها دائمًا بدل سطرٍ ينساه سريعًا.",
    "لا تحتاج إلى موهبة كبيرة، بل إلى ورقة وقلم ودقيقتين فقط من الصمت العميق.",
    "خذ ملاحظة واحدة صغيرة من يومك، وارسم لها دائرة واضحة للفكرة وسهمًا للسبب ومربعًا للنتيجة.",
    "أعد النظر إلى الرسم في المساء، واسأل نفسك: ماذا بقي واضحًا وماذا اختفى؟",
    "أضف سطرًا واحدًا فقط في المساء، ثم دع الورقة تتحدث عنك بعد أسبوع كامل.",
    "ستكتشف أن الرسم أصبح خريطة حقيقية واضحة، كل خط فيها يعيدك إلى لحظة فهمتها لا إلى كلمة حفظتها بعد وقت طويل جدًا.",
    "ابدأ اليوم بورقة واحدة، لا لتتقن الرسم بل لتتذكر ما يستحق أن يبقى.",
]


def run(*args: str, allow_fail: bool = False) -> subprocess.CompletedProcess:
    cmd = [PY, str(ROOT / "rasm.py"), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    tail = (proc.stdout or "")[-4000:] + (proc.stderr or "")[-2000:]
    print(f"$ rasm {' '.join(args)}\n{tail}")
    if proc.returncode != 0 and not allow_fail:
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(args)}")
    return proc


def make_svg(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" '
        'viewBox="0 0 800 600" fill="none" stroke="#2b2723" stroke-width="6" '
        'stroke-linecap="round" stroke-linejoin="round">'
        + body
        + "</svg>",
        encoding="utf-8",
    )


def make_assets() -> None:
    make_svg(
        PD / "assets" / "generated" / "map.svg",
        """
        <path d="M80 470 L210 120 L350 460 L500 110 L720 450"/>
        <path d="M180 300 C 280 210, 390 390, 500 270 S 650 190, 720 260"/>
        <circle cx="350" cy="460" r="28"/>
        <circle cx="500" cy="270" r="18"/>
        <path d="M120 520 L700 520"/>
        """,
    )
    make_svg(
        PD / "assets" / "generated" / "diagram.svg",
        """
        <path d="M90 230 H280 V380 H90 Z"/>
        <path d="M520 230 H710 V380 H520 Z"/>
        <path d="M300 305 L500 305"/>
        <path d="M455 275 L505 305 L455 335"/>
        <path d="M137 305 a48 48 0 1 0 96 0 a48 48 0 1 0 -96 0"/>
        <path d="M610 255 L700 355 M700 255 L610 355"/>
        """,
    )


def write_script_and_research() -> None:
    (PD / "script").mkdir(parents=True, exist_ok=True)
    graph = {
        "lang": "ar",
        "hook": SCENES[0],
        "scenes": [
            {"id": i + 1, "narration": text, "duration": 6.0}
            for i, text in enumerate(SCENES)
        ],
    }
    (PD / "script" / "scriptgraph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    research = {
        "generated_at": "2026-10-21T00:00:00+00:00",
        "project": PROJECT_ID,
        "entities": [
            {
                "name": "خريطة",
                "type": "concept",
                "assets": [
                    {
                        "asset": {
                            "path": "assets/generated/map.svg",
                            "mime": "image/svg+xml",
                            "title": "A hand-drawn route map (generated locally)",
                            "license": "CC0",
                        }
                    }
                ],
            },
            {
                "name": "دائرة",
                "type": "concept",
                "assets": [
                    {
                        "asset": {
                            "path": "assets/generated/diagram.svg",
                            "mime": "image/svg+xml",
                            "title": "A three-part idea diagram (generated locally)",
                            "license": "CC0",
                        }
                    }
                ],
            },
        ],
    }
    (PD / "research").mkdir(parents=True, exist_ok=True)
    (PD / "research" / "research.json").write_text(
        json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    index = [
        {
            "path": "assets/generated/map.svg",
            "sha256": "",
            "kind": "diagram",
            "mime": "image/svg+xml",
            "source": "Generated locally for this sample",
            "url": "",
            "page_url": "",
            "license": "CC0",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "title": "A hand-drawn route map",
            "author": "Rasm sample generator",
            "attr": False,
            "origin": {"kind": "generated"},
        },
        {
            "path": "assets/generated/diagram.svg",
            "sha256": "",
            "kind": "diagram",
            "mime": "image/svg+xml",
            "source": "Generated locally for this sample",
            "url": "",
            "page_url": "",
            "license": "CC0",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "title": "A three-part idea diagram",
            "author": "Rasm sample generator",
            "attr": False,
            "origin": {"kind": "generated"},
        },
    ]
    (PD / "research" / "assets.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def _synth_one(text: str, out: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, "ar-EG-ShakirNeural", rate="-4%").save(str(out))


def synthesize_narration() -> Path:
    tts_dir = PD / "audio" / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    wavs: list[Path] = []
    for i, text in enumerate(SCENES, 1):
        mp3 = tts_dir / f"scene-{i:02d}.mp3"
        wav = tts_dir / f"scene-{i:02d}.wav"
        if not mp3.exists():
            asyncio.run(_synth_one(text, mp3))
        subprocess.run(
            [
                str(FFMPEG), "-y", "-v", "error", "-i", str(mp3),
                "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(wav),
            ],
            check=True,
        )
        wavs.append(wav)

    pauses = [0.65, 0.55, 0.9, 0.45, 0.8, 1.1, 0.5, 0.75, 0.9]
    out = PD / "audio" / "sample-narration.wav"
    params = None
    with wave.open(str(out), "wb") as dst:
        for index, path in enumerate(wavs):
            with wave.open(str(path), "rb") as src:
                if params is None:
                    params = (
                        src.getnchannels(), src.getsampwidth(), src.getframerate()
                    )
                    dst.setnchannels(params[0])
                    dst.setsampwidth(params[1])
                    dst.setframerate(params[2])
                dst.writeframes(src.readframes(src.getnframes()))
            pause = pauses[index] if index < len(pauses) else 0.8
            silence = b"\x00\x00" * int(pause * 48000)
            if index == 0:
                # a short lead-in keeps the first word out of the encoder edge
                pass
            dst.writeframes(silence)
    # prepend 0.35 s of silence
    with wave.open(str(out), "rb") as src:
        frames = src.readframes(src.getnframes())
        params = (src.getnchannels(), src.getsampwidth(), src.getframerate())
    with wave.open(str(out), "wb") as dst:
        dst.setnchannels(params[0])
        dst.setsampwidth(params[1])
        dst.setframerate(params[2])
        dst.writeframes(b"\x00\x00" * int(0.35 * params[2]))
        dst.writeframes(frames)
    return out


def main() -> None:
    if PD.exists():
        shutil.rmtree(PD)
    write_script_and_research()
    make_assets()

    run("plan", PROJECT_ID)
    run("project", "init", PROJECT_ID)
    run("approvals", "import", PROJECT_ID)

    narration = synthesize_narration()
    duration = len(wave.open(str(narration), "rb").readframes(10**9)) / (
        2 * 48000
    )
    if not (60.0 <= duration <= 90.0):
        raise SystemExit(f"sample narration is {duration:.2f}s, need 60-90s")

    run("audio", PROJECT_ID, "--file", str(narration), "--note", "synthetic Arabic TTS sample")
    run("audio", PROJECT_ID, "--normalize", "-16")
    # Rebuild after audio/alignment: scene times now come from the recording.
    run("plan", PROJECT_ID)
    run("project", "link-assets", PROJECT_ID)

    listing = run("approvals", "list", PROJECT_ID, "--json")
    rows = json.loads(listing.stdout)
    for row in rows:
        run(
            "approvals", "approve", PROJECT_ID,
            "--asset", row["asset_id"], "--by", "sample-reviewer",
            "--note", "generated locally; approved for this sample",
        )
    run("approvals", "credits", PROJECT_ID)
    run("plan", PROJECT_ID, "--check")

    out = PD / "render" / "episode.mp4"
    run("render", PROJECT_ID, "--out", str(out), "--size", "1280x720")
    print(f"\nDONE: {out}")
    print(f"narration: {duration:.2f}s")


if __name__ == "__main__":
    main()
