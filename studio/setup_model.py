"""Install the optional portable CPU llama.cpp server and Qwen3 4B GGUF model.

The model is optional: the renderer and Asset Studio run without any LLM.
"""
import argparse
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'
MODELS = ROOT / 'models'

MODEL = 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
MODEL_BASE = 'https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/'
LICENSE_URL = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
LICENSE_NAME = 'LICENSE-APACHE-2.0.txt'


def download(url, dest):
    if dest.exists():
        return
    temp = dest.with_suffix(dest.suffix + '.part')
    req = urllib.request.Request(url, headers={'User-Agent': 'LocalWhiteboardStudio/1.0'})
    with urllib.request.urlopen(req, timeout=180) as src, temp.open('wb') as out:
        shutil.copyfileobj(src, out, 1024 * 1024)
    temp.replace(dest)
    print(dest.name, dest.stat().st_size, flush=True)


def install_runtime():
    for p in (RUNTIME, MODELS):
        p.mkdir(exist_ok=True)
    req = urllib.request.Request(
        'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest',
        headers={'User-Agent': 'LocalWhiteboardStudio/1.0'},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        release = json.load(r)
    choices = [a for a in release['assets'] if a['name'].endswith('bin-win-cpu-x64.zip')]
    if not choices:
        req = urllib.request.Request(
            'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10',
            headers={'User-Agent': 'LocalWhiteboardStudio/1.0'},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            releases = json.load(r)
        for release in releases:
            choices = [a for a in release['assets'] if a['name'].endswith('bin-win-cpu-x64.zip')]
            if choices:
                break
    if not choices:
        raise RuntimeError('No Windows CPU release found')
    asset = choices[0]
    archive = RUNTIME / asset['name']
    download(asset['browser_download_url'], archive)
    if not (RUNTIME / 'llama-server.exe').exists():
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                target = (RUNTIME / member.filename).resolve()
                if not target.is_relative_to(RUNTIME.resolve()):
                    raise ValueError('Invalid archive path')
            z.extractall(RUNTIME)
    return asset['browser_download_url'], release['tag_name']


def install_model():
    download(MODEL_BASE + MODEL, MODELS / MODEL)
    download(LICENSE_URL, MODELS / LICENSE_NAME)


def write_provenance(runtime_url, runtime_version):
    (MODELS / 'provenance.json').write_text(
        json.dumps({
            'model': MODEL_BASE + MODEL,
            'runtime': runtime_url,
            'runtime_version': runtime_version,
            'license': 'Apache-2.0',
            'license_url': 'https://www.apache.org/licenses/LICENSE-2.0',
        }, indent=2),
        encoding='utf-8',
    )


def main():
    ap = argparse.ArgumentParser(description='Install optional local llama.cpp runtime and Qwen3 4B model.')
    ap.add_argument('--no-model', action='store_true', help='Install the runtime only; do not download the 2.4 GB model.')
    args = ap.parse_args()
    runtime_url, runtime_version = install_runtime()
    if not args.no_model:
        install_model()
    write_provenance(runtime_url, runtime_version)
    servers = list(RUNTIME.rglob('llama-server.exe'))
    if not servers:
        raise RuntimeError('Server executable missing')
    print('SERVER', servers[0], flush=True)
    if not (MODELS / MODEL).exists():
        print('MODEL not installed (runtime-only mode)', flush=True)


if __name__ == '__main__':
    main()
