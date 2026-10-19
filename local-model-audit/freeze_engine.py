"""Copy production Python sources read-only into the audit, checking consistent reads."""
import hashlib,json,shutil
from pathlib import Path
BASE=Path(__file__).resolve().parent
SRC=BASE.parent/'rasm-pro'/'engine'
DST=BASE/'engine_snapshot'/'engine'
if DST.exists(): raise SystemExit('Existing frozen snapshot preserved; no overwrite.')
manifest={}
for p in SRC.rglob('*.py'):
    if '__pycache__' in p.parts: continue
    data=p.read_bytes(); digest=hashlib.sha256(data).hexdigest()
    dest=DST/p.relative_to(SRC); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data)
    if hashlib.sha256(p.read_bytes()).hexdigest()!=digest: raise RuntimeError('Source changed during copy: '+str(p))
    manifest[str(p.relative_to(SRC))]=digest
(BASE/'ENGINE-SNAPSHOT.json').write_text(json.dumps({'source':str(SRC),'snapshot':str(DST),'files':manifest,'note':'Exact source copy; runtime paths redirected only in audit process. Original fonts, assets and library are read-only inputs.'},indent=2),encoding='utf-8')
print(len(manifest),'source files frozen')
