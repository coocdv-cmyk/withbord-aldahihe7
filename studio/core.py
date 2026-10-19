from __future__ import annotations
import base64
import io
import json
import math
import os
import re
import shutil
import subprocess
import urllib.request
import uuid
from pathlib import Path

import cv2
import numpy as np
import resvg_py
from PIL import Image, ImageDraw, ImageFont
from arabic_reshaper import reshape
from bidi.algorithm import get_display

ROOT = Path(__file__).resolve().parent
LIB = ROOT / 'library'
DATA = ROOT / 'data'
OUTPUT = ROOT / 'outputs'
for folder in (LIB, DATA, OUTPUT):
    folder.mkdir(exist_ok=True)

# Semantic hints are available offline, even before the language model is installed.
DOMAINS = {
 'finance': ('المال والاقتصاد', ['coins','chart-no-axes-combined','wallet','landmark','piggy-bank','banknote','trending-up','percent'], 'مال فلوس اقتصاد استثمار سعر اسعار تضخم بنك بنوك دخل راتب ادخار دين ديون سوق عملة'),
 'business': ('الأعمال', ['briefcase-business','users','presentation','target','handshake','store','building-2','chart-pie'], 'اعمال شركة شركات مشروع تجارة تسويق مبيعات ادارة فريق عميل عملاء ربح'),
 'religion': ('الدين', ['book-open','moon-star','heart-handshake','sunrise','hand-heart','sparkles','scale','heart'], 'دين اسلام قرآن قران صلاة ايمان صدقة زكاة دعاء يوسف يعقوب الله حديث عبادة'),
 'psychology': ('علم النفس', ['brain','heart','cloud-rain','smile','ear','messages-square','activity','person-standing'], 'نفس نفسي قلق خوف اكتئاب توتر مشاعر سعادة تفكير عقل ذاكرة شعور'),
 'growth': ('التطوير', ['target','trending-up','book-open','graduation-cap','timer','list-checks','lightbulb','rocket'], 'تطوير تعلم مهارة عادة عادات هدف اهداف نجاح انجاز وقت تركيز انتاجية برمجة'),
 'life': ('الحياة', ['house','trees','heart','users','sun','coffee','footprints','sprout'], 'حياة اسرة عائلة بيت صديق اصدقاء علاقة علاقات صحة يوم طبيعة'),
}
ALIASES = {
 'بيت':'house','منزل':'house','بنك':'landmark','مال':'coins','فلوس':'coins','استثمار':'trending-up',
 'اقتصاد':'chart-no-axes-combined','تضخم':'chart-no-axes-combined','ادخار':'piggy-bank',
 'تعلم':'graduation-cap','كتاب':'book-open','قرآن':'book-open','قران':'book-open',
 'صلاة':'moon-star','دين':'moon-star','نفس':'brain','عقل':'brain','تفكير':'brain',
 'هدف':'target','نجاح':'trophy','وقت':'clock','ساعة':'clock','شغل':'briefcase-business',
 'عمل':'briefcase-business','شركة':'building-2','مشروع':'store','فريق':'users',
 'عائلة':'users','ناس':'users','قلب':'heart','صحة':'heart-pulse','خوف':'cloud-rain',
 'سعادة':'smile','نمو':'sprout','تطوير':'rocket','تعليم':'graduation-cap','حياة':'sprout',
 'علم':'flask-conical','تقنية':'cpu','كمبيوتر':'monitor','انترنت':'globe','هاتف':'smartphone',
 'تجارة':'shopping-cart','تسويق':'megaphone','سعر':'tag','ديون':'credit-card',
 'ماء':'droplets','شمس':'sun','قمر':'moon','طريق':'route','مفتاح':'key-round',
}

def catalog():
    p = LIB / 'catalog.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []

def normalize(text):
    text = re.sub('[\u064b-\u065f\u0670ـ]', '', text.lower())
    return text.translate(str.maketrans('أإآىة', 'ااايه'))

def search_assets(query='', domain='', limit=100):
    records = [r for r in catalog() if r.get('review_status')!='rejected']
    q = normalize(query.strip())
    hints = [v for k,v in ALIASES.items() if normalize(k) in q] if q else []
    preferred = DOMAINS.get(domain, ('', [], ''))[1]
    def score(r):
        s = ' '.join([r['id'],r.get('name',''),*r.get('tags',[])])
        return (100 if q and q in normalize(s) else 0) + (80 if r['id'] in hints else 0) + (10 if r['id'] in preferred else 0) + (20 if not q and r.get('kind')=='illustration' else 0)
    records.sort(key=lambda r: (-score(r), r['id']))
    if q:
        records = [r for r in records if score(r) >= 80]
    elif domain:
        records = [r for r in records if r['id'] in preferred or r.get('domain')==domain or (domain=='business' and r.get('domain')=='finance') or (domain=='life' and r.get('domain')=='psychology')]
    return records[:limit]

def choose_assets(text, domain, index):
    pool = {r['id'] for r in catalog()}
    chosen = []
    for word, asset in ALIASES.items():
        if normalize(word) in normalize(text) and asset in pool and asset not in chosen:
            chosen.append(asset)
    defaults = DOMAINS.get(domain, DOMAINS['life'])[1]
    defaults = defaults[index % len(defaults):] + defaults[:index % len(defaults)]
    for asset in defaults:
        if asset in pool and asset not in chosen:
            chosen.append(asset)
    return chosen[:3]

def model_status():
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=1) as r:
            models = json.load(r).get('models', [])
        if any(m['name'].startswith('qwen3:0.6b') for m in models):
            return {'ready': True, 'provider':'ollama', 'name':'qwen3:0.6b'}
    except Exception:
        pass
    try:
        with urllib.request.urlopen('http://127.0.0.1:11435/health', timeout=1) as r:
            if json.load(r).get('status') == 'ok':
                return {'ready': True, 'provider':'llama', 'name':'Qwen3 0.6B Q4'}
    except Exception:
        pass
    return {'ready':False, 'name':'المخطط المحلي بالقواعد'}

def llm_scenes(originals, domain, progress=None):
    status = model_status()
    if not status['ready']:
        raise ValueError('النموذج غير مشغل. استخدم تشغيل النموذج أو المخطط السريع.')
    ids = list(dict.fromkeys(DOMAINS.get(domain, DOMAINS['life'])[1]+list(ALIASES.values())))
    refined=[]
    for offset in range(len(originals)):
        if callable(progress):progress(offset,len(originals))
        batch=originals[offset:offset+1]
        refined.extend(llm_batch(batch,ids,status))
    return refined

def llm_batch(batch,ids,status):
    schema={'type':'object','properties':{'scenes':{'type':'array','minItems':len(batch),'maxItems':len(batch),
            'items':{'type':'object','properties':{'title':{'type':'string'},
            'assets':{'type':'array','minItems':3,'maxItems':3,'items':{'type':'string','enum':ids}}},
            'required':['title','assets'],'additionalProperties':False}}},'required':['scenes'],'additionalProperties':False}
    prompt = ('/no_think\nCreate one storyboard title per input passage. Titles in Arabic, 3 to 6 words. '
              'Do not invent facts. Return exactly '+str(len(batch))+' scenes in the original order. '
              'Return JSON only: {"scenes":[{"title":"عنوان قصير", '
              '"assets":["icon-id","icon-id","icon-id"]}]}. '
              'Choose icons from: '+','.join(ids)+'. Passages:\n'+
              json.dumps([s['text'] for s in batch],ensure_ascii=False))
    if status['provider'] == 'ollama':
        url = 'http://127.0.0.1:11434/api/chat'
        payload = {'model':'qwen3:0.6b','messages':[{'role':'user','content':prompt}],
                   'stream':False, 'think':False,'format':schema,'options':{'num_predict':4096,'temperature':0.2}}
    else:
        url = 'http://127.0.0.1:11435/v1/chat/completions'
        payload = {'messages':[{'role':'user','content':prompt}], 'temperature':0.2,'max_tokens':4096,
                   'response_format':{'type':'json_schema','json_schema':{'name':'storyboard','strict':True,'schema':schema}}}
    req = urllib.request.Request(url, json.dumps(payload).encode(), {'Content-Type':'application/json'})
    keyfile=DATA/'model-key.txt'
    if status['provider']=='llama' and keyfile.exists():
        req.add_header('Authorization','Bearer '+keyfile.read_text().strip())
    with urllib.request.urlopen(req, timeout=240) as r:
        result = json.load(r)
    content = result['message']['content'] if status['provider']=='ollama' else result['choices'][0]['message']['content']
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.S).strip()
    obj = json.loads(content[content.find('{'):content.rfind('}')+1])
    scenes = obj.get('scenes')
    if not isinstance(scenes, list) or len(scenes)!=len(batch) or any(not isinstance(s,dict) for s in scenes):
        raise ValueError('النموذج أعاد خطة غير صالحة؛ جرّب المخطط السريع.')
    for s,original in zip(scenes,batch):
        s['text']=original['text']
    return scenes

def validate_project(p):
    if not isinstance(p, dict):
        raise ValueError('ملف المشروع غير صالح')
    if p.get('renderer','legacy') not in ('legacy','whiteboard'):
        raise ValueError('أسلوب إخراج غير صالح')
    if p.get('paper','cream') not in ('cream','white'):
        raise ValueError('خلفية غير صالحة')
    if not isinstance(p.get('hand',True),bool) or not isinstance(p.get('camera',True),bool):
        raise ValueError('إعدادات اليد والكاميرا غير صالحة')
    if p.get('resolution') not in ('720p','1080p','vertical'):
        raise ValueError('اختر دقة صالحة')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(p.get('accent',''))):
        raise ValueError('لون غير صالح')
    scenes = p.get('scenes', [])
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 120:
        raise ValueError('عدد المشاهد يجب أن يكون بين 1 و120')
    total = 0
    for s in scenes:
        d = float(s.get('duration',0))
        if not math.isfinite(d) or d < 1 or d > 3600:
            raise ValueError('مدة المشهد يجب أن تكون بين ثانية وساعة')
        total += d
        for field in ('title','text'):
            if not isinstance(s.get(field,''), str) or len(s.get(field,'')) > 20000:
                raise ValueError('نص المشهد غير صالح')
        if s.get('layout','row') not in ('row','focus','steps','compare'):
            raise ValueError('قالب غير صالح')
        if not isinstance(s.get('assets',[]), list) or len(s.get('assets',[])) > 6:
            raise ValueError('حد المشهد 6 أصول')
        for a in s.get('assets',[]):
            if not isinstance(a,str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', a):
                raise ValueError('اسم أصل غير صالح')
            if not (LIB/(a+'.svg')).exists() and not (LIB/(a+'.png')).exists():
                raise ValueError('الأصل غير موجود: '+a)
        placements=s.get('placements',{})
        if not isinstance(placements,dict) or len(placements)>6:
            raise ValueError('مواضع غير صالحة')
        for entry in placements.values():
            if not isinstance(entry,dict): raise ValueError('موضع غير صالح')
            for key,low,high in [('x',.05,.95),('y',.2,.88),('size',.04,.6)]:
                value=float(entry.get(key, .2 if key=='size' else .5))
                if not math.isfinite(value) or not low<=value<=high:
                    raise ValueError('موضع أو حجم خارج الحدود')
        labels=s.get('labels',{})
        if not isinstance(labels,dict) or len(labels)>6 or any(not isinstance(v,str) or len(v)>60 for v in labels.values()):
            raise ValueError('أسماء الأصول غير صالحة؛ الحد 60 حرفًا للاسم')
    if total > 7200:
        raise ValueError('حد المشروع الحالي ساعتان')
    return p

def plan(opts):
    script = str(opts.get('script','')).strip()
    duration = float(opts.get('duration',60))
    if not script or len(script) > 60000:
        raise ValueError('أدخل سكريبت من 1 إلى 60000 حرف')
    if not math.isfinite(duration) or not 5 <= duration <= 7200:
        raise ValueError('مدة الفيديو من 5 إلى 7200 ثانية')
    target = float(opts.get('scene_length',15))
    if not math.isfinite(target) or not 5 <= target <= 60:
        raise ValueError('مدة المشهد المقترحة من 5 إلى 60 ثانية')
    count = min(120, max(1, round(duration/target)), max(1,len(script.split())//5))
    domain = opts.get('domain','life')
    if domain not in DOMAINS:
        domain = 'life'
    engine = opts.get('planner','rules')
    # Choose boundaries at sentences; long paragraphs are split only when necessary.
    quota=max(15,math.ceil(len(script.split())/count))
    sentences=[]
    for sentence in re.split(r'(?<=[.!؟؛\n])\s*',script):
        words=sentence.split()
        if len(words)>max(80,quota*2):
            sentences.extend(' '.join(words[i:i+quota]) for i in range(0,len(words),quota))
        elif words:
            sentences.append(' '.join(words))
    count=min(count,len(sentences))
    cumulative=np.cumsum([len(s.split()) for s in sentences])
    boundaries=[0]
    for k in range(1,count):
        candidates=range(boundaries[-1]+1,len(sentences)-(count-k)+1)
        boundary=min(candidates,key=lambda b:abs(cumulative[b-1]-cumulative[-1]*k/count))
        boundaries.append(boundary)
    boundaries.append(len(sentences))
    groups=[' '.join(sentences[a:b]) for a,b in zip(boundaries,boundaries[1:])]
    if engine=='ai' and any(len(t)>7000 for t in groups):
        raise ValueError('المشهد أطول من سياق النموذج الصغير؛ قلل متوسط مدة المشهد أو استخدم المخطط السريع')
    scenes = [{'text':t, 'title':' '.join(t.split()[:7])} for t in groups]
    if engine == 'ai':
        scenes = llm_scenes(scenes,domain,opts.get('_on_progress'))
    pool = {r['id'] for r in catalog()}
    weights = [max(1,len(str(s.get('text','')).split())) for s in scenes]
    for i,s in enumerate(scenes):
        s['title'] = str(s.get('title',''))[:240]
        s['text'] = str(s.get('text',''))
        if engine=='ai':
            # A tiny model can emit emoji, other scripts, or unrelated headings.
            # Keep only headings grounded in the original passage and drawable by the Arabic font.
            title=s['title']
            unsupported=re.search(r'[^\u0600-\u06ff\u0750-\u077f\u08a0-\u08ffA-Za-z0-9\s.,:;!?؟،؛()٪%\-–—«»]',title)
            words=re.findall(r'[\w]+',normalize(title))
            if not title.strip() or unsupported or any(word not in normalize(s['text']) for word in words if len(word)>2):
                s['title']=' '.join(s['text'].split()[:7])
        s['duration'] = 1 + (duration-len(scenes))*weights[i]/sum(weights)
        proposed=[a for a in s.get('assets',[]) if isinstance(a,str) and a in pool]
        s['assets']=list(dict.fromkeys(proposed+choose_assets(s['text'],domain,i)))[:3]
        if opts.get('renderer','whiteboard')=='whiteboard':
            from whiteboard import suggest_story
            story=suggest_story(s['text'],domain,i)
            if story:s['assets']=story
        s['layout'] = ['row','focus','steps'][i%3]
    result = {'version':1,'id':uuid.uuid4().hex,'title':str(opts.get('title','مشروعي'))[:120],
              'script':script,'domain':domain,'duration':duration,'planner':engine,
              'resolution':opts.get('resolution','1080p'),'accent':opts.get('accent','#149e91'),
              'renderer':opts.get('renderer','whiteboard'),'hand':opts.get('hand',True),
              'camera':opts.get('camera',True),'paper':opts.get('paper','cream'),'scenes':scenes}
    return validate_project(result)

def dimensions(project):
    return {'720p':(1280,720),'1080p':(1920,1080),'vertical':(1080,1920)}[project['resolution']]

def font(size):
    for name in ('tahoma.ttf','arial.ttf','segoeui.ttf'):
        p = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
        if p.exists():
            return ImageFont.truetype(str(p),max(10,round(size)))
    return ImageFont.load_default()

def display(text):
    return get_display(reshape(text))

def text_lines(draw, text, f, width, max_lines=3):
    lines, line = [], ''
    for word in text.split():
        test = (line+' '+word).strip()
        if draw.textbbox((0,0),display(test),font=f)[2] > width and line:
            lines.append(line); line=word
        else:
            line=test
    if line:
        lines.append(line)
    if len(lines)>max_lines:
        lines=lines[:max_lines]; lines[-1]+=' …'
    return lines

def asset_image(asset, size, accent):
    svg = LIB / f'{asset}.svg'
    png = LIB / f'{asset}.png'
    if svg.exists():
        source = svg.read_text(encoding='utf-8').replace('currentColor','#182b40')
        raw = resvg_py.svg_to_bytes(svg_string=source, width=size, height=size)
        return Image.open(io.BytesIO(bytes(raw))).convert('RGBA')
    if png.exists():
        im=Image.open(png).convert('RGBA'); im.thumbnail((size,size)); return im
    return Image.new('RGBA',(size,size))

def compose(project, index):
    if project.get('renderer')=='whiteboard':
        from whiteboard import preview
        return preview(project,index)
    return compose_legacy(project,index)

def compose_legacy(project, index):
    w,h = dimensions(project)
    scale = w/1280
    im = Image.new('RGB',(w,h),'white')
    dr = ImageDraw.Draw(im)
    scene = project['scenes'][index]
    accent=project['accent']
    f=font(w*.037 if w>h else w*.052)
    lines=text_lines(dr,scene['title'],f,w*.84,3)
    y=h*.09
    regions=[]
    for line in lines:
        dr.text((w/2,y),display(line),font=f,anchor='mt',fill='#182b40')
        y+=f.size*1.5
    dr.rounded_rectangle((w*.44,y+12*scale,w*.56,y+18*scale),radius=3*scale,fill=accent)
    regions.append((0,0,w,round(y+25*scale)))
    assets=scene.get('assets',[])[:6]
    n=len(assets)
    if w<h:
        centers=([(w*.5,h*(.36+j*.18)) for j in range(n)] if n<=3 else
                 [(w*(.3+.4*(j%2)),h*(.36+.18*(j//2))) for j in range(n)])
        size=int(w*(.25 if n<=3 else .22))
    elif scene.get('layout')=='focus' and n>=3:
        centers=[(w*.5,h*.55),(w*.19,h*.66),(w*.81,h*.66)]+[(w*(.2+.3*j),h*.83) for j in range(max(0,n-3))]
        size=int(min(w*.17,h*.30))
    else:
        centers=[(w*(1-(j+1)/(n+1)),h*(.56 if scene.get('layout')!='steps' else .50+.075*j)) for j in range(n)]
        size=int(min(w/(n+1)*.65,h*.28))
    for j,(asset,(cx,cy)) in enumerate(zip(assets,centers)):
        placement=scene.get('placements',{}).get(str(j),{})
        cx=float(placement.get('x',cx/w))*w
        cy=float(placement.get('y',cy/h))*h
        item_size=int(float(placement.get('size',size/w))*w)
        icon=asset_image(asset,item_size,accent)
        x,y0=round(cx-icon.width/2),round(cy-icon.height/2)
        if j:
            px,py=centers[j-1]
            # Thin connecting line behind the visual blocks.
            if w>h and scene.get('layout')=='steps':
                dr.line((px-size*.6,py,cx+size*.6,cy),fill=accent,width=max(2,round(3*scale)))
        im.paste(icon,(x,y0),icon)
        dr.ellipse((cx-5*scale,cy+item_size*.64,cx+5*scale,cy+item_size*.64+10*scale),fill=accent)
        regions.append((max(0,x-10),max(0,y0-10),min(w,x+item_size+10),min(h,round(cy+item_size*.72+15))))
    dr.text((w*.06,h*.94),f'{index+1:02d}',font=font(19*scale),fill='#718096',anchor='lm')
    return im,regions

def find_ffmpeg():
    local=ROOT/'runtime/ffmpeg.exe'
    if local.exists():
        return str(local)
    exe=shutil.which('ffmpeg')
    if exe:
        return exe
    base=Path(os.environ.get('LOCALAPPDATA',''))/'Microsoft/WinGet/Packages'
    matches=list(base.glob('Gyan.FFmpeg*/ffmpeg*/bin/ffmpeg.exe'))
    if matches:
        return str(matches[0])
    raise RuntimeError('FFmpeg غير موجود؛ ثبّته ثم أعد التشغيل')

def stroke_map(image,regions):
    # Walk contours rather than wipe rectangles. Each region is revealed in order.
    arr=np.array(image)
    ink=(arr.min(axis=2)<245).astype(np.uint8)*255
    h,w=ink.shape
    timing=np.ones((h,w),dtype=np.float32)
    occupied=np.zeros((h,w),dtype=np.uint8)
    all_regions=regions+[(0,0,w,h)]
    spans=[]
    for x0,y0,x1,y1 in all_regions:
        mask=np.zeros_like(ink); mask[y0:y1,x0:x1]=ink[y0:y1,x0:x1]
        mask[occupied>0]=0
        contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
        contours=sorted(contours,key=lambda c:(cv2.boundingRect(c)[1]//80,-cv2.boundingRect(c)[0]))
        if contours:
            spans.append((contours,mask))
        occupied|=mask
    for ri,(contours,mask) in enumerate(spans):
        total=sum(len(c) for c in contours) or 1
        done=0
        # Scatter ordered samples, then thicken to cover antialiasing and fills.
        seeds=np.ones((h,w),dtype=np.float32)
        for c in contours:
            pts=c[:,0,:]
            values=(ri+(done+np.arange(len(pts)))/total)/len(spans)
            seeds[pts[:,1],pts[:,0]]=values
            done+=len(pts)
        # Filled interiors receive a short late fill pass; contour outlines draw first.
        outline=cv2.erode(seeds,np.ones((9,9),np.uint8))
        selected=mask>0
        timing[selected]=np.minimum(outline[selected],(ri+.94)/len(spans))
    return arr,timing,ink>0

def render_project(project, job, cancel):
    if project.get('renderer')=='whiteboard':
        from whiteboard import render
        return render(project,job,cancel)
    validate_project(project)
    ffmpeg=find_ffmpeg()
    run=OUTPUT/uuid.uuid4().hex
    run.mkdir()
    (run/'project.json').write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
    used={a for s in project['scenes'] for a in s.get('assets',[])}
    (run/'asset-credits.json').write_text(json.dumps([r for r in catalog() if r['id'] in used],ensure_ascii=False,indent=2),encoding='utf-8')
    fps=24
    # Frame allocation fixes drift across hundreds of scenes.
    endframes=np.rint(np.cumsum([float(s['duration']) for s in project['scenes']])*fps).astype(int)
    framecounts=np.diff(np.r_[0,endframes])
    def stamp(frame):
        ms=round(int(frame)*1000/fps)
        hours,ms=divmod(ms,3600000);minutes,ms=divmod(ms,60000);seconds,ms=divmod(ms,1000)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}'
    subtitles=[]
    for i,s in enumerate(project['scenes']):
        subtitles.append(f'{i+1}\n{stamp(0 if i==0 else endframes[i-1])} --> {stamp(endframes[i])}\n{s["text"]}\n')
    (run/'captions.srt').write_text('\n'.join(subtitles),encoding='utf-8')
    clips=[]
    w,h=dimensions(project)
    for i,s in enumerate(project['scenes']):
        if cancel.is_set():
            raise RuntimeError('تم إلغاء التصدير')
        job.update(message=f'رسم المشهد {i+1} من {len(project["scenes"])}',progress=round(i/len(project['scenes'])*95))
        im,regions=compose(project,i)
        im.save(run/f'scene_{i+1:03d}.png')
        arr,timing,ink=stroke_map(im,regions)
        clip=run/f'scene_{i+1:03d}.mp4'
        frames=int(framecounts[i]); drawframes=max(1,round(frames*.74))
        cmd=[ffmpeg,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}',
             '-r',str(fps),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','19',
             '-pix_fmt','yuv420p','-movflags','+faststart',str(clip)]
        with (run/'encoder.log').open('ab') as log:
            proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for frame in range(frames):
                    if cancel.is_set():
                        raise RuntimeError('تم إلغاء التصدير')
                    p=min(1.,frame/max(1,drawframes-1))
                    if frame>=drawframes:
                        out=arr
                    else:
                        mask=cv2.compare(timing,p,cv2.CMP_LE)
                        out=np.full_like(arr,255)
                        cv2.copyTo(arr,mask,out)
                    proc.stdin.write(out.tobytes())
                    if frame%24==0:
                        job['progress']=round((i+frame/frames)/len(project['scenes'])*95)
                proc.stdin.close()
                if proc.wait()!=0:
                    raise RuntimeError('فشل الترميز؛ راجع encoder.log')
            except BaseException:
                proc.kill(); proc.wait(); raise
        clips.append(clip)
    job.update(message='تجميع الفيديو الصامت',progress=97)
    manifest=run/'concat.txt'
    manifest.write_text('\n'.join("file '"+c.name+"'" for c in clips),encoding='utf-8')
    out=run/'video.mp4'
    result=subprocess.run([ffmpeg,'-y','-v','error','-f','concat','-safe','0','-i',str(manifest),
                           '-c','copy','-movflags','+faststart',str(out)],capture_output=True,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-1000:])
    job.update(status='done',progress=100,message='الفيديو جاهز',url=f'/outputs/{run.name}/video.mp4',
               folder=str(run),clips=[f'/outputs/{run.name}/{c.name}' for c in clips])

def import_image(name,encoded):
    data=base64.b64decode(encoded,validate=True)
    if len(data)>15_000_000:
        raise ValueError('حجم الصورة يجب أن يقل عن 15 ميجابايت')
    with Image.open(io.BytesIO(data)) as source:
        source.load()
        source.thumbnail((2048,2048))
        im=source.convert('RGBA')
    aid='custom-'+uuid.uuid4().hex[:12]
    im.save(LIB/f'{aid}.png')
    records=catalog()
    records.append({'id':aid,'name':str(name)[:120],'source':'استيراد المستخدم',
                    'license':'يحددها المستخدم','tags':str(name).split(),'file':aid+'.png','kind':'illustration'})
    tmp=LIB/'catalog.tmp'
    tmp.write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8'); tmp.replace(LIB/'catalog.json')
    return aid
