import json
import threading
from core import DATA,render_project
from demo import project

p=project();(DATA/(p['id']+'.json')).write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
job={};render_project(p,job,threading.Event())
(DATA/'whiteboard-demo-result.json').write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
print(job['folder'],flush=True)
