import sys, json, shutil, hashlib, time, copy
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=BASE.parent/'rasm-pro'
snap=BASE/'snapshot'
snap.mkdir(exist_ok=True)
shutil.copytree(ROOT/'engine',snap/'engine',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'engine').rglob('*.py')}
(BASE/'source-hashes.json').write_text(json.dumps(hashes,indent=2))
sys.path.insert(0,str(snap))
import engine.core.paths as paths
paths.FONTS=ROOT/'assets/fonts'
paths.LIBRARY=ROOT/'library'
paths.CACHE=BASE/'cache'
paths.LOGS=BASE/'logs'
for p in (paths.CACHE,paths.LOGS):p.mkdir(exist_ok=True)
from engine.render.director import Director
from engine.stages.plan import build_plan
from PIL import Image,ImageDraw
def save(name,obj): (BASE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def txt(s,rect):return {'type':'text','text':s,'font':'cairo','size':100,'rtl':False,'rect':rect,'gap':.15}
scenes=[
 {'id':1,'duration':10,'elements':[{'type':'highlight','rect':[180,230,2100,230],'events':False},txt('Why did the war spread?',[180,230,2100,230]),{'type':'underline','rect':[180,230,2100,230]},txt('One event. Several alliances.\nA chain of decisions.',[250,750,2060,350])]},
 {'id':2,'duration':10,'elements':[{'type':'paper_card','rect':[230,260,2100,850]},txt('ARCHIVE / 1939–1945',[400,380,1760,200]),txt('An image needs context:\nwho, where, when, and why.',[400,770,1760,300])]},
 {'id':3,'duration':10,'elements':[txt('Read the sequence',[300,120,1960,220]),{'type':'timeline','font':'cairo','rtl':False,'size':100,'rect':[250,600,2060,420],'events':[{'label':'1939','sub':'War begins'},{'label':'1945','sub':'War ends'}]}]}
]
plan={'lang':'en','canvas':[2560,1440],'fps':24,'scenes':scenes}
save('english-plan.json',plan)
report=Director(copy.deepcopy(plan),fps=24,out_size=(1280,720),preset='ultrafast').render(BASE/'english-three-styles.mp4')
save('english-render.json',report)
auto=build_plan({'lang':'en','scenes':[{'id':1,'narration':'Why did the war spread across several continents after a chain of political decisions?','duration':10}]},{})
save('automatic-english-plan.json',auto)
# Limited endurance probe: actual ten-minute output, reduced 2fps/640x360.
# This is deliberately NOT a full-quality long-film certification.
long={'scenes':[{'id':i+1,'duration':10,'elements':[txt('Chapter '+str(i+1)+' / Evidence before conclusions',[250,500,2060,350])]} for i in range(60)]}
t=time.perf_counter()
r=Director(long,fps=2,out_size=(640,360),preset='ultrafast').render(BASE/'ten-minute-reduced-load.mp4')
r['scope']='600 seconds, 2 fps, 640x360, 60 text scenes; no narration or mux; not production-quality endurance proof'
r['wall_seconds']=time.perf_counter()-t
save('endurance-render.json',r)
after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'engine').rglob('*.py')}
save('source-comparison.json',{'changed_during_run':[k for k in hashes if hashes[k]!=after.get(k)],'snapshot_files':len(hashes)})
print(json.dumps({'english':report,'endurance':r},ensure_ascii=False))
