import json
import time
import urllib.request
from pathlib import Path

BASE='http://127.0.0.1:8765'
def get(path):
    with urllib.request.urlopen(BASE+path,timeout=10) as r:return json.load(r)
token=get('/api/status')['token']
def post(path,data):
    req=urllib.request.Request(BASE+path,json.dumps(data).encode(),{'Content-Type':'application/json','X-Studio-Token':token})
    with urllib.request.urlopen(req,timeout=240) as r:return json.load(r)

script='الادخار يبدأ بتحديد أهداف واضحة. خصص جزءا من دخلك لصندوق الطوارئ. الاستثمار يحتاج فهم المخاطر وتنويع الأصول.'
start=time.monotonic()
p=post('/api/plan',{'title':'تجربة التخطيط الذكي','script':script,'duration':18,'scene_length':5,'domain':'finance','planner':'ai','resolution':'1080p'})
assert ' '.join(s['text'] for s in p['scenes'])==script
assert abs(sum(s['duration'] for s in p['scenes'])-18)<1e-6
post('/api/save',p)
assert get('/api/project/'+p['id'])['script']==script
print('AI_AND_SAVE_OK',round(time.monotonic()-start,2),len(p['scenes']),flush=True)
job=post('/api/generate',{'prompt':'a simple open book with a small plant','style':'flat','steps':10,'guidance':7,'seed':1000})
print('GENERATION_JOB',job['id'],flush=True)
(Path(__file__).parent/'data/generation-check.json').write_text(json.dumps(job))
