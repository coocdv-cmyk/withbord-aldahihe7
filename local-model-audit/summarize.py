"""Read-only scoring aids; output stays in audit directory."""
import json,re
from pathlib import Path
BASE=Path(__file__).resolve().parent
summary={}
for run in (BASE/'results').iterdir():
    if not run.is_dir() or not (run/'environment.json').exists(): continue
    items=[]
    for p in sorted(run.glob('*.json')):
        r=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(r,dict) or 'request' not in r or 'name' not in r: continue
        obj=r.get('parsed'); text=(r.get('response',{}).get('choices') or [{}])[0].get('message',{}).get('content','')
        items.append({'case':r['name'],'seconds':r['seconds'],'finish_reason':r.get('finish_reason'),'json_valid':isinstance(obj,dict),'output':obj,'raw_if_invalid':text[:4000] if not obj else None,'usage':r.get('response',{}).get('usage')})
    summary[run.name]={'cases':items}
    for name in ('native_integration','direct_plan_execution','strict_plan_execution','strict_model_video_result','agent_history','agent_state','production_integrity','local_image_tool_result','image_generation_execution','icon_tool_result'):
        p=run/(name+'.json')
        if p.exists(): summary[run.name][name]=json.loads(p.read_text(encoding='utf-8'))
(BASE/'RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:{'calls':len(v['cases']),'json_valid':sum(x['json_valid'] for x in v['cases']),'seconds':round(sum(x['seconds'] for x in v['cases']),1),'integrity':v.get('production_integrity'),'agent_actions':[x.get('action',x.get('error')) for x in v.get('agent_history',[])]} for k,v in summary.items()},ensure_ascii=True,indent=2))
