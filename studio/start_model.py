import os
import subprocess
import secrets
from pathlib import Path
root=Path(__file__).resolve().parent
servers=list((root/'runtime').rglob('llama-server.exe'))
model=root/'models/Qwen3-0.6B-Q4_K_M.gguf'
if not servers or not model.exists():
    raise SystemExit('Run studio/setup_model.py first')
keyfile=root/'data/model-key.txt'
if not keyfile.exists(): keyfile.write_text(secrets.token_urlsafe(40))
subprocess.run([str(servers[0]),'-m',str(model),'--host','127.0.0.1','--port','11435',
                '-c','8192','-t',str(max(1,min(8,(os.cpu_count() or 4)-1))),
                '--jinja','--reasoning-budget','0','--parallel','1',
                '--api-key-file',str(keyfile),'--cors-origins','http://127.0.0.1:8765'],check=True)
