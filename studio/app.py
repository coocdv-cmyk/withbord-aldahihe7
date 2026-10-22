"""Loopback-only desktop web application. Run with the project's .venv Python."""
import argparse
import io
import json
import re
import mimetypes
import secrets
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core import ROOT, LIB, DATA, OUTPUT, catalog, compose, plan, model_status, validate_project, render_project, import_image, search_assets

TOKEN=secrets.token_urlsafe(32)
JOBS={}
LOCK=threading.Lock()
MUTATION=threading.Lock()

def remote_search(query):
    params=urllib.parse.urlencode({'action':'query','format':'json','generator':'search',
         'gsrsearch':query,'gsrnamespace':6,'gsrlimit':16,'prop':'imageinfo','iiprop':'url|extmetadata','iiurlwidth':400})
    req=urllib.request.Request('https://commons.wikimedia.org/w/api.php?'+params,
                              headers={'User-Agent':'LocalWhiteboardStudio/1.0 (asset discovery)'})
    with urllib.request.urlopen(req,timeout=30) as r:
        data=json.load(r)
    out=[]
    for page in data.get('query',{}).get('pages',{}).values():
        info=page.get('imageinfo',[{}])[0]; meta=info.get('extmetadata',{})
        out.append({'title':page['title'],'url':info.get('url',''),'thumb':info.get('thumburl',''),
                    'page':info.get('descriptionurl',''),'license':meta.get('LicenseShortName',{}).get('value','راجع المصدر'),
                    'artist':meta.get('Artist',{}).get('value','')})
    return out

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self,data,status=200,kind='application/json; charset=utf-8'):
        if not isinstance(data,bytes):
            data=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        host=self.headers.get('Host','')
        expected=f'127.0.0.1:{self.server.server_port}'
        return host in (expected,f'localhost:{self.server.server_port}')

    def send_file(self,target):
        size=target.stat().st_size; start=0;end=size-1;status=200
        requested=self.headers.get('Range','')
        if requested:
            import re
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
            if not match or not any(match.groups()):
                return self.send({'error':'Invalid range'},416)
            a,b=match.groups()
            if a:
                start=int(a);end=min(end,int(b)) if b else end
            else:
                start=max(0,size-int(b))
            if start>end or start>=size:
                return self.send({'error':'Invalid range'},416)
            status=206
        self.send_response(status)
        self.send_header('Content-Type',mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(end-start+1))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('X-Content-Type-Options','nosniff')
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with target.open('rb') as source:
                source.seek(start);remaining=end-start+1
                while remaining:
                    chunk=source.read(min(65536,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            pass

    def do_GET(self):
        if not self.allowed():
            return self.send({'error':'Invalid host'},403)
        parsed=urllib.parse.urlparse(self.path)
        path=urllib.parse.unquote(parsed.path)
        query=urllib.parse.parse_qs(parsed.query)
        try:
            if path=='/api/status':
                records=[r for r in catalog() if r.get('review_status')!='rejected']
                return self.send({'token':TOKEN,'assets':len(records),'illustrations':sum(r.get('kind')=='illustration' for r in records),'model':model_status()})
            if path=='/api/demo':
                from demo import project
                return self.send(project(query.get('name',['yusuf'])[0]))
            if path=='/api/demo-result':
                manifest=DATA/'whiteboard-demo-result.json'
                if not manifest.exists():return self.send({'error':'العينة المصدرة غير موجودة بعد'},404)
                result=json.loads(manifest.read_text(encoding='utf-8'))
                folder=Path(result['folder']).resolve()
                if not folder.is_relative_to(OUTPUT.resolve()):raise ValueError('Invalid output folder')
                result['project']=json.loads((folder/'project.json').read_text(encoding='utf-8'))
                return self.send(result)
            if path=='/api/assets':
                results=search_assets(query.get('q',[''])[0],query.get('domain',[''])[0],3000)
                kind=query.get('kind',['all'])[0]
                if kind=='illustration':results=[r for r in results if r.get('kind')=='illustration']
                if kind=='icon':results=[r for r in results if r.get('source')=='Lucide']
                return self.send(results[:180])
            if path=='/api/projects':
                return self.send([{'file':p.stem,'title':json.loads(p.read_text(encoding='utf-8')).get('title','')}
                                  for p in sorted(DATA.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
                                  if p.stem.isalnum() and len(p.stem)==32])
            if path.startswith('/api/project/'):
                name=path.rsplit('/',1)[-1]
                if not name.isalnum():
                    raise ValueError('Invalid project')
                return self.send(json.loads((DATA/(name+'.json')).read_text(encoding='utf-8')))
            if path.startswith('/api/job/'):
                with LOCK:
                    job=dict(JOBS[path.rsplit('/',1)[-1]][0])
                return self.send(job)
            if path=='/':
                return self.send((ROOT/'web/studio-v2.html').read_bytes(),kind='text/html; charset=utf-8')
            bases={'/web/':ROOT/'web','/library/':LIB,'/outputs/':OUTPUT}
            for prefix,base in bases.items():
                if path.startswith(prefix):
                    target=(base/path[len(prefix):]).resolve()
                    if not target.is_relative_to(base.resolve()) or not target.is_file():
                        return self.send({'error':'Not found'},404)
                    if target.suffix not in ('.js','.css','.svg','.png','.mp4','.json','.txt','.srt'):
                        return self.send({'error':'Not found'},404)
                    return self.send_file(target)
            return self.send({'error':'Not found'},404)
        except Exception as exc:
            self.send({'error':str(exc)},400)

    def do_POST(self):
        if not self.allowed() or self.headers.get('X-Studio-Token')!=TOKEN:
            return self.send({'error':'Unauthorized'},403)
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
            return self.send({'error':'Invalid origin'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<22_000_000:
                raise ValueError('حجم الطلب غير صالح')
            data=json.loads(self.rfile.read(size))
            path=urllib.parse.urlparse(self.path).path
            if path=='/api/plan':
                return self.send(plan(data))
            if path=='/api/plan-start':
                import uuid
                with LOCK:
                    if any(j[0]['status']=='running' for j in JOBS.values()):
                        raise ValueError('انتظر اكتمال المهمة الحالية أو ألغِها')
                    jid=uuid.uuid4().hex;cancel=threading.Event()
                    job={'status':'running','kind':'planning','progress':0,'message':'تقسيم النص وتجهيز خطة الرسم'}
                    JOBS[jid]=(job,cancel)
                def planning():
                    try:
                        def progress(index,total):
                            if cancel.is_set():raise RuntimeError('تم إلغاء التخطيط')
                            job.update(progress=round(index/max(1,total)*95),message=f'فهم المشهد {index+1} من {total}')
                        data['_on_progress']=progress
                        result=plan(data)
                        job.update(status='done',progress=100,message='خطة الرسم جاهزة للمراجعة',project=result)
                    except Exception as exc:job.update(status='error',message=str(exc))
                threading.Thread(target=planning,daemon=True).start()
                return self.send({'id':jid})
            if path=='/api/preview':
                project=validate_project(data['project'])
                index=int(data.get('index',0))
                im,_=compose(project,index)
                im.thumbnail((960,960))
                buf=io.BytesIO(); im.save(buf,format='PNG')
                return self.send(buf.getvalue(),kind='image/png')
            if path=='/api/save':
                p=validate_project(data)
                ident=str(p.get('id',''))
                if not ident.isalnum() or len(ident)>80:
                    raise ValueError('Invalid project id')
                with MUTATION:
                    dest=DATA/(ident+'.json'); tmp=dest.with_suffix('.tmp')
                    tmp.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(dest)
                return self.send({'saved':True,'id':ident})
            if path=='/api/import':
                with MUTATION:
                    aid=import_image(data['name'],data['data'])
                return self.send({'id':aid})
            if path=='/api/search-online':
                return self.send(remote_search(str(data.get('query',''))[:200]))
            if path=='/api/generate':
                import subprocess,uuid,base64
                settings={'prompt':str(data.get('prompt','')).strip()[:500],
                          'style':data.get('style','flat'),'steps':int(data.get('steps',15)),
                          'guidance':float(data.get('guidance',7)),'seed':int(data.get('seed',1000))}
                if not settings['prompt'] or settings['style'] not in ('line','flat','doodle'):
                    raise ValueError('أدخل وصفًا وحدد ستايل صالحًا')
                if not 5<=settings['steps']<=40 or not 1<=settings['guidance']<=15 or not 0<=settings['seed']<=2147483647:
                    raise ValueError('إعدادات توليد خارج الحدود')
                with LOCK:
                    if any(j[0]['status']=='running' for j in JOBS.values()):
                        raise ValueError('انتظر اكتمال المهمة الحالية')
                    jid=uuid.uuid4().hex; cancel=threading.Event()
                    job={'status':'running','progress':0,'message':'توليد محلي على المعالج؛ قد يستغرق عدة دقائق'}
                    JOBS[jid]=(job,cancel)
                generation_dir=DATA/'generations'; generation_dir.mkdir(exist_ok=True)
                request=generation_dir/(jid+'.generation.json')
                request.write_text(json.dumps(settings),encoding='utf-8')
                def generate():
                    try:
                        exe=ROOT.parent/'.venv-gen/Scripts/python.exe'
                        if not exe.exists(): raise ValueError('بيئة توليد الصور غير موجودة')
                        with request.with_suffix('.log').open('wb') as log:
                            proc=subprocess.Popen([str(exe),str(ROOT/'generate_asset.py'),str(request)],
                                 stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                            started=time.monotonic()
                            while proc.poll() is None:
                                if cancel.wait(1) or time.monotonic()-started>1800:
                                    proc.kill(); proc.wait(); raise RuntimeError('تم إيقاف التوليد')
                            if proc.returncode:
                                raise RuntimeError('تعذر التوليد. تحقق من أوزان SD1.5 المحلية وسجل '+request.with_suffix('.log').name)
                        with MUTATION:
                            aid=import_image(settings['prompt'],base64.b64encode(request.with_suffix('.png').read_bytes()).decode())
                            records=catalog()
                            for record in records:
                                if record['id']==aid:
                                    record.update(source='SD1.5 local generation',license='CreativeML OpenRAIL-M',review_status='pending')
                            (LIB/'catalog.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
                            (LIB/(aid+'.generation.json')).write_text(json.dumps(settings,ensure_ascii=False),encoding='utf-8')
                        job.update(status='done',progress=100,message='الأصل جاهز للمراجعة',asset=aid)
                    except Exception as exc:
                        job.update(status='error',message=str(exc))
                threading.Thread(target=generate,daemon=True).start()
                return self.send({'id':jid})
            if path=='/api/import-online':
                url=data.get('thumb') or data['url']; u=urllib.parse.urlparse(url)
                if u.scheme!='https' or u.hostname!='upload.wikimedia.org':
                    raise ValueError('الاستيراد المباشر يدعم ملفات Wikimedia فقط')
                req=urllib.request.Request(url,headers={'User-Agent':'LocalWhiteboardStudio/1.0'})
                with urllib.request.urlopen(req,timeout=45) as r:
                    if urllib.parse.urlparse(r.url).hostname!='upload.wikimedia.org':
                        raise ValueError('Invalid redirect')
                    raw=r.read(15_000_001)
                import base64
                with MUTATION:
                    aid=import_image(data.get('title','Online asset'),base64.b64encode(raw).decode())
                    # Keep source, attribution and license alongside the imported image.
                    records=catalog()
                    records[-1].update(source=data.get('page',url),license=data.get('license',''),artist=data.get('artist',''))
                    (LIB/'catalog.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
                return self.send({'id':aid})
            if path in ('/api/render','/api/preview-motion'):
                if path=='/api/preview-motion':
                    project=validate_project(data['project'])
                    index=int(data.get('index',0))
                    selected=dict(project['scenes'][index])
                    selected['duration']=min(6.,float(selected['duration']))
                    project=dict(project,scenes=[selected],resolution='720p',duration=selected['duration'])
                else:project=validate_project(data)
                import uuid
                with LOCK:
                    if any(j[0]['status']=='running' for j in JOBS.values()):
                        raise ValueError('يوجد تصدير قيد التشغيل؛ انتظر أو ألغِه')
                    jid=uuid.uuid4().hex; cancel=threading.Event()
                    job={'status':'running','progress':0,'message':'بدء التصدير'}
                    JOBS[jid]=(job,cancel)
                def work():
                    try:
                        render_project(project,job,cancel)
                    except Exception as exc:
                        job.update(status='error',message=str(exc))
                threading.Thread(target=work,daemon=True).start()
                return self.send({'id':jid})
            if path=='/api/rasm/understand':
                import rasm_bridge
                script=str(data.get('script','')).strip()
                pid=str(data.get('project_id') or data.get('id',''))
                if not re.match(r'^[A-Za-z0-9_-]{1,80}$', pid):
                    raise ValueError('Invalid project id')
                res=rasm_bridge.understand_script(script,pid,offline=bool(data.get('offline',True)))
                return self.send({'ok':True,'project_id':pid,'scenes':res['graph'].get('stats',{}).get('scenes',0)})
            if path=='/api/rasm/research':
                import rasm_bridge
                pid=str(data.get('project_id') or data.get('id',''))
                if not re.match(r'^[A-Za-z0-9_-]{1,80}$', pid):
                    raise ValueError('Invalid project id')
                res=rasm_bridge.research_project(pid,max_entities=int(data.get('max_entities',14)),download=bool(data.get('download',False)))
                return self.send({'ok':True,'project_id':pid,'totals':res.get('totals',{})})
            if path=='/api/rasm/narration/import':
                import base64,uuid,rasm_bridge
                pid=str(data.get('project_id') or data.get('id',''))
                if not re.match(r'^[A-Za-z0-9_-]{1,80}$', pid):
                    raise ValueError('Invalid project id')
                name=str(data.get('name','narration.wav'))[:120]
                raw=base64.b64decode(str(data.get('data','')),validate=True)
                if len(raw)>200_000_000:
                    raise ValueError('Audio too large')
                tmp=DATA/(uuid.uuid4().hex+'.upload'+Path(name).suffix)
                tmp.write_bytes(raw)
                try:
                    man=rasm_bridge.import_narration_studio(pid,str(tmp),copy=True,deep=bool(data.get('deep',True)),note=str(data.get('note',''))[:200])
                finally:
                    try:tmp.unlink()
                    except Exception:pass
                return self.send({'ok':True,'project_id':pid,'narration':{k:man.get(k) for k in ('path','sha256','sample_rate','channels','total_samples','duration_exact','duration_sec','codec','alignment_level','alignment_segments','alignment_error')}})
            if path=='/api/rasm/plan':
                import rasm_bridge
                pid=str(data.get('project_id') or data.get('id',''))
                if not re.match(r'^[A-Za-z0-9_-]{1,80}$', pid):
                    raise ValueError('Invalid project id')
                plan=rasm_bridge.build_plan_studio(pid,max_scenes=data.get('max_scenes'),fps=data.get('fps'))
                proj=rasm_bridge.rasm_to_studio_project(plan,pid)
                return self.send({'ok':True,'project_id':pid,'project':proj,'timing':plan.get('timing',{}),'fps':plan.get('fps')})
            if path=='/api/rasm/approvals':
                import rasm_bridge
                pid=str(data.get('project_id') or data.get('id',''))
                if not re.match(r'^[A-Za-z0-9_-]{1,80}$', pid):
                    raise ValueError('Invalid project id')
                state=rasm_bridge.asset_approvals_studio(pid)
                return self.send({'ok':True,'project_id':pid,'approvals':state})
            if path=='/api/rasm/status':
                import rasm_bridge
                pid=str(data.get('project_id') or data.get('id',''))
                if not re.match(r'^[A-Za-z0-9_-]{1,80}$', pid):
                    raise ValueError('Invalid project id')
                return self.send({'ok':True,'status':rasm_bridge.production_status_studio(pid)})
            if path=='/api/rasm/render':
                import uuid,rasm_bridge
                pid=str(data.get('project_id') or data.get('id',''))
                if not re.match(r'^[A-Za-z0-9_-]{1,80}$', pid):
                    raise ValueError('Invalid project id')
                run=OUTPUT/uuid.uuid4().hex; run.mkdir()
                out=run/'video.mp4'
                raw_size=data.get('size',(1280,720))
                if not isinstance(raw_size,(list,tuple)) or len(raw_size)!=2:
                    raise ValueError('Invalid size')
                size=(int(raw_size[0]),int(raw_size[1]))
                if not (16<=size[0]<=4096 and 16<=size[1]<=4096):
                    raise ValueError('Invalid size')
                fps=data.get('fps')  # None → the plan's rational rate
                mode=str(data.get('mode') or 'preview')
                if mode not in ('preview','final'):
                    raise ValueError('Invalid mode')
                res=rasm_bridge.render_project_studio(pid,out_path=str(out),fps=fps,size=size,max_seconds=data.get('max_seconds'),mode=mode)
                report=rasm_bridge.validate_studio_render(res,size,expect_audio=bool(res.get('audio')))
                if not report.get('ok'):
                    raise RuntimeError('Render validation failed: '+'; '.join(c['check'] for c in report.get('checks',[]) if not c['ok']))
                return self.send({'ok':True,'project_id':pid,'url':f'/outputs/{run.name}/video.mp4','folder':str(run),'result':{k:res.get(k) for k in ('frames','seconds','duration_sec_exact','fps','render_seconds','narration_frames','drift_frames','plan_path','manifest','audio','mode') if k in res},'validation':report})
            if path=='/api/cancel':
                JOBS[data['id']][1].set()
                return self.send({'ok':True})
            return self.send({'error':'Not found'},404)
        except Exception as exc:
            self.send({'error':str(exc)},400)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8765); parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Whiteboard Studio: http://127.0.0.1:{args.port}',flush=True)
    if not args.no_browser:
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    server.serve_forever()
