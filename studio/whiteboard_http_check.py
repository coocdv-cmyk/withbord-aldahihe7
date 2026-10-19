import json
import time
import urllib.request
from pathlib import Path

BASE='http://127.0.0.1:8765'
def get(path):
    with urllib.request.urlopen(BASE+path,timeout=10) as r:return json.load(r)
status=get('/api/status');token=status['token']
def post(path,data):
    req=urllib.request.Request(BASE+path,json.dumps(data).encode(),{'Content-Type':'application/json','X-Studio-Token':token})
    with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
def wait(jid):
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        job=get('/api/job/'+jid)
        if job['status']=='error':raise RuntimeError(job['message'])
        if job['status']=='done':return job
        time.sleep(.3)
    raise TimeoutError('Local job exceeded test deadline')

art=get('/api/assets?kind=illustration');assert len(art)>=10
demo=get('/api/demo?name=yusuf');assert len(demo['scenes'])==4 and demo['scenes'][3]['layout']=='compare'
script='الادخار يساعد على تنظيم المال. التعلم المستمر يطور المهارات.'
started=time.monotonic()
task=post('/api/plan-start',{'script':script,'duration':16,'scene_length':8,'domain':'finance','planner':'ai','renderer':'whiteboard','resolution':'720p'})
planned=wait(task['id'])['project']
assert ' '.join(s['text'] for s in planned['scenes'])==script
assert planned['renderer']=='whiteboard' and planned['scenes'][0]['assets'][0].startswith('story-')
post('/api/save',planned)
assert get('/api/project/'+planned['id'])['script']==script
result={'illustrations':len(art),'planning_seconds':round(time.monotonic()-started,2),'async_plan':'passed','save_restore':'passed'}
(Path(__file__).parent/'data/whiteboard-http-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
