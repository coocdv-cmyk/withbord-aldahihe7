"""Read-only validation of sources/videos; writes reports only in this prototype."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT.parents[1]
SOURCE = Path(r'C:\Users\USER\Downloads\shadow-procedural-v2\v2')
FFMPEG = Path(r'D:\withbord inmation\studio\runtime\ffmpeg.exe')
FFPROBE = FFMPEG.with_name('ffprobe.exe')


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def main():
    expected = json.loads((ROOT / 'reports/source_sha256.json').read_text(encoding='utf-8-sig'))
    isolation = {
        'source_files_checked': len(expected),
        'downloads_differences': [n for n, h in expected.items() if digest(SOURCE / n) != h],
        'snapshot_differences': [n for n, h in expected.items() if digest(ROOT / 'source_snapshot' / n) != h],
        'engine_python_differences': [],
        'note': 'This task wrote only inside shadow-motion-v4. Engine differences may be concurrent work; no files are reverted.'
    }
    before = json.loads((ROOT / 'reports/engine_before.json').read_text(encoding='utf-8-sig'))
    for name, h in before.items():
        if digest(ENGINE / name) != h:
            isolation['engine_python_differences'].append(name)
    (ROOT / 'reports/isolation_report.json').write_text(json.dumps(isolation, indent=2), encoding='utf-8')
    videos = []
    for p in sorted((ROOT / 'preview').glob('*.mp4')):
        info = subprocess.run([str(FFPROBE), '-v', 'error', '-show_format', '-show_streams', '-count_frames', '-of', 'json', str(p)], capture_output=True, text=True, check=True)
        data = json.loads(info.stdout)
        decode = subprocess.run([str(FFMPEG), '-v', 'error', '-i', str(p), '-f', 'null', '-'], capture_output=True, text=True)
        stream = next(s for s in data['streams'] if s['codec_type'] == 'video')
        audio = next((s for s in data['streams'] if s['codec_type'] == 'audio'), None)
        item = {'file': p.name, 'video_codec': stream['codec_name'], 'width': stream['width'], 'height': stream['height'], 'fps': stream['avg_frame_rate'], 'frames': int(stream['nb_read_frames']), 'video_duration': float(stream['duration']), 'audio_codec': audio['codec_name'] if audio else None, 'audio_duration': float(audio['duration']) if audio else None, 'full_decode_passed': decode.returncode == 0 and not decode.stderr.strip(), 'decoder_stderr': decode.stderr.strip()}
        item['av_duration_difference'] = abs(item['video_duration'] - item['audio_duration']) if audio else None
        item['passed'] = item['full_decode_passed'] and item['width'] == 1280 and item['height'] == 720 and item['fps'] == '30/1' and (not audio or item['av_duration_difference'] <= 1/30 + .002)
        videos.append(item)
    report = {'passed': len(videos) == 3 and all(v['passed'] for v in videos), 'videos': videos, 'isolation': isolation}
    (ROOT / 'reports/media_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not report['passed'] or isolation['downloads_differences'] or isolation['snapshot_differences']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
