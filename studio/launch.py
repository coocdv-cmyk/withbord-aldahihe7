"""One-click launcher; does not install software or download anything."""
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

root=Path(__file__).resolve().parent
flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
def running(url):
    try:
        with urllib.request.urlopen(url,timeout=1) as r:return r.status==200
    except Exception:return False

def start(script,name):
    with (root/'data'/f'{name}.log').open('ab') as log:
        subprocess.Popen([sys.executable,str(root/script),'--no-browser'] if script=='app.py' else
                         [sys.executable,str(root/script)],cwd=root.parent,stdout=log,stderr=log,creationflags=flags)

if not running('http://127.0.0.1:11435/health') and (root/'models/Qwen3-0.6B-Q4_K_M.gguf').exists():
    start('start_model.py','model-launch')
if not running('http://127.0.0.1:8765/api/status'):
    start('app.py','studio-launch')
for _ in range(30):
    if running('http://127.0.0.1:8765/api/status'):break
    time.sleep(.4)
webbrowser.open('http://127.0.0.1:8765')
