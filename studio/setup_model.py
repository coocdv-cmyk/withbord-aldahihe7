"""Install a portable CPU llama.cpp server and an official Qwen GGUF model."""
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'runtime'
MODELS=ROOT/'models'

def download(url,dest):
    if dest.exists():
        return
    temp=dest.with_suffix(dest.suffix+'.part')
    req=urllib.request.Request(url,headers={'User-Agent':'LocalWhiteboardStudio/1.0'})
    with urllib.request.urlopen(req,timeout=180) as src,temp.open('wb') as out:
        shutil.copyfileobj(src,out,1024*1024)
    temp.replace(dest)
    print(dest.name,dest.stat().st_size,flush=True)

def install():
    for p in (RUNTIME,MODELS): p.mkdir(exist_ok=True)
    req=urllib.request.Request('https://api.github.com/repos/ggml-org/llama.cpp/releases/latest',headers={'User-Agent':'LocalWhiteboardStudio/1.0'})
    with urllib.request.urlopen(req,timeout=30) as r: release=json.load(r)
    choices=[a for a in release['assets'] if a['name'].endswith('bin-win-cpu-x64.zip')]
    if not choices:
        req=urllib.request.Request('https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10',headers={'User-Agent':'LocalWhiteboardStudio/1.0'})
        with urllib.request.urlopen(req,timeout=30) as r: releases=json.load(r)
        for release in releases:
            choices=[a for a in release['assets'] if a['name'].endswith('bin-win-cpu-x64.zip')]
            if choices: break
    if not choices: raise RuntimeError('No Windows CPU release found')
    asset=choices[0]; archive=RUNTIME/asset['name']
    download(asset['browser_download_url'],archive)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            target=(RUNTIME/member.filename).resolve()
            if not target.is_relative_to(RUNTIME.resolve()): raise ValueError('Invalid archive path')
        z.extractall(RUNTIME)
    model='Qwen3-0.6B-Q4_K_M.gguf'
    base='https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/'
    download(base+model,MODELS/model)
    download('https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/LICENSE',MODELS/'QWEN-LICENSE.txt')
    (MODELS/'provenance.json').write_text(json.dumps({'model':base+model,'runtime':asset['browser_download_url'],
        'runtime_version':release['tag_name'],'license':'Apache-2.0'},indent=2),encoding='utf-8')
    servers=list(RUNTIME.rglob('llama-server.exe'))
    if not servers: raise RuntimeError('Server executable missing')
    print('SERVER',servers[0],flush=True)

if __name__=='__main__': install()
