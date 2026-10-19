"""Inspect produced plans/media without modifying them."""
import json,hashlib,re,wave
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parent
out={}
for run in (BASE/'results').iterdir():
    if not run.is_dir(): continue
    data={}
    for p in run.glob('*_plan.json'):
        plan=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(plan,dict) or 'canvas' not in plan or not isinstance(plan.get('scenes'),list): continue
        issues=[]; text_items=[]
        for sc in plan.get('scenes',[]):
            els=sc.get('elements',[])
            for i,el in enumerate(els):
                if el.get('type')!='text': continue
                text_items.append(el.get('text',''))
                if re.search('[\u0600-\u06ff]',el.get('text','')) and not el.get('rtl',True): issues.append({'scene':sc.get('id'),'issue':'Arabic text has rtl=false','text':el['text']})
                for prev in els[:i]:
                    if prev.get('type')=='text' and prev.get('rect')==el.get('rect'): issues.append({'scene':sc.get('id'),'issue':'text rectangles exactly overlap','texts':[prev.get('text'),el.get('text')]})
        data[p.name]={'scenes':len(plan.get('scenes',[])),'texts':text_items,'issues':issues}
    for p in run.glob('*.sfx.json'):
        obj=json.loads(p.read_text(encoding='utf-8')); scenes=obj.get('scenes',[])
        duration=max((x.get('start',0)+x.get('seconds',0) for x in scenes),default=0)
        events=obj.get('events',[])
        data[p.name]={'duration':duration,'events':len(events),'event_max_t':max((e.get('t',0) for e in events),default=0),'events_after_duration':sum(e.get('t',0)>duration+0.001 for e in events)}
    for p in run.glob('*.sfx.wav'):
        with wave.open(str(p),'rb') as w:
            buf=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.int32)
            data[p.name]={'seconds':w.getnframes()/w.getframerate(),'sample_peak':int(np.max(np.abs(buf))) if len(buf) else 0,'clipped_samples':int(np.sum(np.abs(buf)>=32767))}
    if data: out[run.name]=data
manifest=json.loads((BASE/'ENGINE-SNAPSHOT.json').read_text(encoding='utf-8'))
changed=[name for name,digest in manifest['files'].items() if hashlib.sha256((Path(manifest['snapshot'])/name).read_bytes()).hexdigest()!=digest]
out['frozen_engine_integrity']={'unchanged':not changed,'changed':changed}
(BASE/'ARTIFACT-CHECKS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:list(v) if isinstance(v,dict) else v for k,v in out.items()},ensure_ascii=True))
