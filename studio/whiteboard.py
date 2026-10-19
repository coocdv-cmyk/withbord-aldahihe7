"""Local whiteboard renderer: ordered ink paths, pencil-tip compositor, board camera.

Raster paths are an approximation, not the original artist's pen strokes. Geometry,
timing, hand alignment and camera remain independently editable and testable.
"""
from __future__ import annotations
import hashlib
import json
import math
import subprocess
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from skimage.morphology import skeletonize

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'art/cache'
CACHE.mkdir(parents=True,exist_ok=True)
PAPER=np.array([248,244,234],dtype=np.uint8)
STORY_RULES=[
    ('بئر جب دلو حبل', ['story-well','story-boy']),
    ('يعقوب اباه ابيه ابنه انتظار حزن', ['story-elder','story-shirt']),
    ('قافله قافلة مصر تجار جمال باعوه', ['story-caravan']),
    ('قميص قميصي قماش', ['story-shirt','story-elder']),
    ('يوسف صبي غلام حلم رؤيا', ['story-boy','story-well']),
]

def suggest_story(text,domain,index):
    from core import normalize,catalog
    pool={r['id'] for r in catalog() if r.get('kind')=='illustration' and r.get('review_status')=='approved'}
    n=normalize(text)
    for terms,ids in STORY_RULES:
        if any(normalize(t) in n for t in terms.split()) and all(i in pool for i in ids):
            return ids
    # Do not invent a historical drawing for an unrelated business/psychology script.
    fallback={'finance':'story-business','business':'story-business','psychology':'story-mind',
              'growth':'story-learning','life':'story-mind','religion':'story-shirt'}
    aid=fallback.get(domain)
    return [aid] if aid in pool else []

def paper(w,h,theme='cream'):
    if theme=='white': return np.full((h,w,3),255,dtype=np.uint8)
    rng=np.random.default_rng(37)
    grain=rng.integers(-1,2,size=(h,w,1),dtype=np.int16)
    return np.clip(PAPER.astype(np.int16)+grain,0,255).astype(np.uint8)

def _fit_asset(asset,box):
    from core import asset_image
    im=asset_image(asset,max(box),'#315d50')
    # Production cutout compositing: suppress translucent generator halos.
    rgba=np.array(im)
    rgba[:,:,3]=np.where(rgba[:,:,3]>=245,255,0).astype(np.uint8)
    im=Image.fromarray(rgba)
    alpha=im.getchannel('A')
    bounds=alpha.getbbox()
    if bounds:im=im.crop(bounds)
    im.thumbnail(box,Image.Resampling.LANCZOS)
    return im

def compose(project,index):
    from core import dimensions,font,display,text_lines
    w,h=dimensions(project); portrait=h>w
    scene=project['scenes'][index]
    im=Image.new('RGB',(w,h),'white');dr=ImageDraw.Draw(im)
    accent=project.get('accent','#315d50')
    f=font(w*(.042 if not portrait else .052))
    lines=text_lines(dr,scene['title'],f,w*.83,2)
    ty=h*.065
    regions=[]
    for line in lines:
        dr.text((w*.5,ty),display(line),font=f,anchor='mt',fill='#23382e')
        ty+=f.size*1.35
    dr.line((w*.37,ty+8,w*.63,ty+8),fill=accent,width=max(2,round(w*.002)))
    title_region=(int(w*.06),int(h*.04),int(w*.94),int(ty+22))
    assets=scene.get('assets',[])[:6]
    n=len(assets)
    # Compose a dominant illustration plus supporting elements, with a shared baseline.
    if n==1:
        presets=[(.5,.59,.78 if 'caravan' in assets[0] else .55,.64)]
    elif n==2:
        presets=[(.66,.58,.55,.64),(.25,.62,.29,.49)]
    else:
        presets=[(.65,.55,.51,.62),(.24,.57,.29,.46),(.35,.80,.24,.22),
                 (.83,.81,.18,.18),(.14,.82,.16,.17),(.48,.37,.17,.18)]
    if scene.get('layout')=='compare' and n<=3:
        presets=[(1-(j+1)/(n+1),.56,.25,.58) for j in range(n)]
    if portrait:
        presets=[(.5,.40,.66,.35),(.5,.72,.57,.27),(.19,.73,.22,.16),
                 (.81,.73,.22,.16),(.22,.49,.2,.16),(.78,.49,.2,.16)]
    for j,asset in enumerate(assets):
        cx,cy,bw,bh=presets[j]
        label=scene.get('labels',{}).get(str(j),'')
        p=scene.get('placements',{}).get(str(j),{})
        if label and not p:
            cy=min(cy,.56);bh=min(bh,.58)
        cx=float(p.get('x',cx));cy=float(p.get('y',cy))
        if 'size' in p:
            bw=float(p['size']);bh=min(.7,bw*w/h)
        art=_fit_asset(asset,(max(20,round(w*bw)),max(20,round(h*bh))))
        x=round(cx*w-art.width/2);y=round(cy*h-art.height/2)
        im.paste(art,(x,y),art)
        regions.append((max(0,x-4),max(0,y-4),min(w,x+art.width+4),min(h,y+art.height+4)))
        if label:
            lf=font(w*.021)
            ly=min(h*.90,y+art.height+10)
            dr.text((cx*w,ly),display(label),font=lf,anchor='mt',fill=accent)
            regions.append((max(0,round(cx*w-w*.14)),round(ly),min(w,round(cx*w+w*.14)),min(h,round(ly+lf.size*1.5))))
    # A quiet ground line links the drawings without turning the composition into an icon row.
    dr.line((w*.12,h*.91,w*.88,h*.91),fill='#b6b5a0',width=max(1,round(w*.001)))
    dr.text((w*.06,h*.955),f'{index+1:02d}',font=font(w*.015),fill='#6e7d70',anchor='lm')
    # Let the illustration lead; the headline is written after the story objects.
    regions.append(title_region)
    return im,regions

def preview(project,index):
    image,regions=compose(project,index)
    arr=np.array(image)
    bg=paper(image.width,image.height,project.get('paper','cream'))
    coverage=255-arr.min(axis=2)
    # White background disappears; internal light surfaces remain clean paper.
    bg[coverage>5]=arr[coverage>5]
    return Image.fromarray(bg),regions

def prepare(image,regions):
    """Return reveal times and a pen trajectory from the centre lines of dark ink."""
    original=np.array(image)
    w,h=image.size
    key=hashlib.sha256(b'paths-v6'+original.tobytes()+json.dumps(regions).encode()).hexdigest()
    path=CACHE/(key+'.npz')
    if path.exists():
        with np.load(path,allow_pickle=False) as z:
            return z['timing'].astype(np.float32),z['trajectory'],z['breaks']
    factor=min(1.,900/w)
    sw,sh=max(1,round(w*factor)),max(1,round(h*factor))
    small=cv2.resize(original,(sw,sh),interpolation=cv2.INTER_AREA)
    dark=small.max(axis=2)<110
    dark|=cv2.Canny(cv2.cvtColor(small,cv2.COLOR_RGB2GRAY),90,180)>0
    occupied=np.zeros((sh,sw),bool)
    pixel_order=np.full((sh,sw),np.inf,dtype=np.float32)
    paths=[];breaks=[];counter=0
    # Region order is semantic. Within a region, automatic topology approximates pen order.
    for region in regions+[(0,0,w,h)]:
        x0,y0,x1,y1=[int(round(v*factor)) for v in region]
        x0=max(0,x0);y0=max(0,y0);x1=min(sw,x1);y1=min(sh,y1)
        if x1<=x0 or y1<=y0:continue
        ink=np.zeros_like(dark);ink[y0:y1,x0:x1]=dark[y0:y1,x0:x1]
        ink&=~occupied;occupied|=ink
        skel=skeletonize(ink)
        contours,_=cv2.findContours(skel.astype(np.uint8),cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
        contours=sorted(contours,key=lambda c:(cv2.boundingRect(c)[1]//max(20,sh//13),-cv2.boundingRect(c)[0]))
        for c in contours:
            pts=c[:,0,:]
            if not len(pts):continue
            # Traverse each connected centre line rather than erasing a rectangle.
            values=np.arange(counter,counter+len(pts),dtype=np.float32)
            np.minimum.at(pixel_order,(pts[:,1],pts[:,0]),values)
            breaks.append(counter);paths.append(pts.astype(np.float32));counter+=len(pts)
    if not paths:
        trajectory=np.array([[w/2,h/2]],dtype=np.float32)
        timing=np.ones((h,w),dtype=np.float32)
        return timing,trajectory,np.array([0],dtype=np.int32)
    trajectory=np.concatenate(paths)/factor
    seed=np.isfinite(pixel_order)
    # Nearest-centreline propagation covers stroke width while preserving original antialiasing.
    _,labels=cv2.distanceTransformWithLabels((~seed).astype(np.uint8),cv2.DIST_L2,5,labelType=cv2.DIST_LABEL_PIXEL)
    lookup=np.ones(int(labels.max())+1,dtype=np.float32)
    lookup[labels[seed]]=pixel_order[seed]/max(1,counter-1)*.78
    ink_timing=lookup[labels]
    timing_small=np.full((sh,sw),1.1,dtype=np.float32)
    expanded=cv2.dilate(dark.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
    timing_small[expanded]=ink_timing[expanded]
    # Colour enters only after ink. Each semantic object gets a short fill interval.
    colour=(small.min(axis=2)<248)&~expanded
    done=np.zeros_like(colour)
    valid=[r for r in regions if r[2]>r[0] and r[3]>r[1]]+[(0,0,w,h)]
    for ri,(x0,y0,x1,y1) in enumerate(valid):
        x0,y0,x1,y1=[int(round(v*factor)) for v in (x0,y0,x1,y1)]
        x0=max(0,x0);y0=max(0,y0);x1=min(sw,x1);y1=min(sh,y1)
        if x1<=x0 or y1<=y0:continue
        mask=np.zeros_like(colour);mask[y0:y1,x0:x1]=colour[y0:y1,x0:x1];mask&=~done;done|=mask
        yy,xx=np.nonzero(mask)
        timing_small[yy,xx]=.80+.19*(ri+(xx-x0)/max(1,x1-x0))/len(valid)
    timing=cv2.resize(timing_small,(w,h),interpolation=cv2.INTER_NEAREST)
    np.savez_compressed(path,timing=timing,trajectory=trajectory,breaks=np.array(breaks,dtype=np.int32))
    return timing,trajectory,np.array(breaks,dtype=np.int32)

class Pencil:
    def __init__(self,width):
        path=ROOT/'art/drawing-hand.png'
        self.image=None
        if path.exists():
            im=Image.open(path).convert('RGBA')
            # Calibrated on the inspected cutout. Tip is exposed in the UI as an asset setting.
            settings=json.loads((ROOT/'art/hand.json').read_text())
            scale=width*.38/im.width
            self.image=np.array(im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS))
            self.image[:,:,3]=np.where(self.image[:,:,3]>=245,255,0).astype(np.uint8)
            self.anchor=(round(settings['tip'][0]*self.image.shape[1]),round(settings['tip'][1]*self.image.shape[0]))

    def overlay(self,frame,tip):
        if self.image is None:return frame
        h,w=frame.shape[:2];art=self.image
        x=round(tip[0]-self.anchor[0]);y=round(tip[1]-self.anchor[1])
        x0=max(0,x);y0=max(0,y);x1=min(w,x+art.shape[1]);y1=min(h,y+art.shape[0])
        if x1<=x0 or y1<=y0:return frame
        piece=art[y0-y:y1-y,x0-x:x1-x]
        alpha=piece[:,:,3:4].astype(np.float32)/255
        roi=frame[y0:y1,x0:x1]
        roi[:]=(piece[:,:,:3]*alpha+roi*(1-alpha)).astype(np.uint8)
        return frame

def _ease(t):
    t=max(0.,min(1.,t));return t*t*(3-2*t)

def camera_rect(index,count,w,h,progress,enabled=True):
    slots=[(1,0),(0,0),(0,1),(1,1)]
    if count==1 or not enabled:return (0.,0.,float(w),float(h))
    x,y=slots[index%4]
    focus=np.array([x*w,y*h,w,h],dtype=float)
    def view(painted):
        if painted<=1:return np.array([w,0,w,h],dtype=float)
        if painted==2:return np.array([0,-h*.5,2*w,2*h],dtype=float)
        return np.array([0,0,2*w,2*h],dtype=float)
    overview=view(index%4+1)
    previous=view(max(1,index%4))
    if progress<.07:
        return tuple(previous+(focus-previous)*_ease(progress/.07))
    if progress>.90:
        return tuple(focus+(overview-focus)*_ease((progress-.90)/.10))
    return tuple(focus)

def crop_camera(board,rect,w,h):
    x,y,rw,rh=rect
    matrix=np.array([[w/rw,0,-x*w/rw],[0,h/rh,-y*h/rh]],dtype=np.float32)
    return cv2.warpAffine(board,matrix,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=tuple(int(c) for c in board[0,0]))

def render(project,job,cancel):
    from core import validate_project,dimensions,find_ffmpeg,catalog,OUTPUT
    validate_project(project)
    start=time.monotonic();run=OUTPUT/uuid.uuid4().hex;run.mkdir()
    (run/'project.json').write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
    used={a for s in project['scenes'] for a in s['assets']}
    (run/'asset-credits.json').write_text(json.dumps([r for r in catalog() if r['id'] in used],ensure_ascii=False,indent=2),encoding='utf-8')
    w,h=dimensions(project);fps=24;ffmpeg=find_ffmpeg();scenes=project['scenes']
    end=np.rint(np.cumsum([float(s['duration']) for s in scenes])*fps).astype(int)
    counts=np.diff(np.r_[0,end]);clips=[];slots=[(1,0),(0,0),(0,1),(1,1)]
    camera=project.get('camera',True)
    pencil=Pencil(w) if project.get('hand',True) else None
    board=None;subtitles=[]
    def stamp(frame):
        ms=round(int(frame)*1000/fps);hh,ms=divmod(ms,3600000);mm,ms=divmod(ms,60000);ss,ms=divmod(ms,1000)
        return f'{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}'
    for index,scene in enumerate(scenes):
        if cancel.is_set():raise RuntimeError('تم إلغاء التصدير')
        local=index%4;page_count=min(4,len(scenes)-(index//4)*4)
        if local==0:
            board=paper(w*2,h*2,project.get('paper','cream'))
        job.update(message=f'تجهيز مسارات المشهد {index+1} من {len(scenes)}',progress=round(index/len(scenes)*95))
        image,regions=compose(project,index)
        final,_=preview(project,index);final.save(run/f'scene_{index+1:03d}.png')
        arr=np.array(image);timing,path,breaks=prepare(image,regions)
        foreground=(arr.min(axis=2)<248).astype(np.uint8)*255
        bg=paper(w,h,project.get('paper','cream'))
        frames=int(counts[index]);draw_start=.07 if camera and page_count>1 else .01;draw_end=.83
        clip=run/f'scene_{index+1:03d}.mp4'
        cmd=[ffmpeg,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}',
             '-r',str(fps),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(clip)]
        with (run/'encoder.log').open('ab') as log:
            proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for frame in range(frames):
                    if cancel.is_set():raise RuntimeError('تم إلغاء التصدير')
                    fraction=frame/max(1,frames-1)
                    p=max(0.,min(1.,(fraction-draw_start)/(draw_end-draw_start)))
                    tile=bg.copy();mask=cv2.bitwise_and(cv2.compare(timing,p,cv2.CMP_LE),foreground);cv2.copyTo(arr,mask,tile)
                    sx,sy=slots[local] if page_count>1 else (0,0)
                    tx=sx*w;ty=sy*h
                    board[ty:ty+h,tx:tx+w]=tile
                    if not camera or page_count==1:
                        out=tile
                        rect=(0,0,w,h);tx=ty=0
                    else:
                        rect=camera_rect(local,page_count,w,h,fraction,True)
                        out=crop_camera(board,rect,w,h)
                    if pencil and draw_start<fraction<draw_end and 0<p<.78 and len(path)>1:
                        at=min(len(path)-1,round(p/.78*(len(path)-1)))
                        # Lift the pen across disconnected paths, rather than visibly drawing a join.
                        near_break=np.any(np.abs(breaks-at)<1)
                        if not near_break:
                            point=path[at]
                            x=(point[0]+tx-rect[0])*w/rect[2];y=(point[1]+ty-rect[1])*h/rect[3]
                            pencil.overlay(out,(x,y))
                    proc.stdin.write(out.tobytes())
                    if frame%24==0:job.update(message=f'رسم وتلوين المشهد {index+1} من {len(scenes)}',progress=round((index+frame/frames)/len(scenes)*95))
                    if index==0 and frame in (max(1,frames//3),max(1,frames*2//3)):
                        Image.fromarray(out).save(run/f'proof_{frame:04d}.png')
                proc.stdin.close()
                if proc.wait()!=0:raise RuntimeError('فشل ترميز الفيديو؛ راجع encoder.log')
            except BaseException:
                proc.kill();proc.wait();raise
        clips.append(clip)
        if local==3 or index==len(scenes)-1:
            Image.fromarray(board).save(run/f'board_{index//4+1:03d}.png')
        subtitles.append(f'{index+1}\n{stamp(0 if index==0 else end[index-1])} --> {stamp(end[index])}\n{scene["text"]}\n')
    if board is not None:Image.fromarray(board).save(run/'board.png')
    (run/'captions.srt').write_text('\n'.join(subtitles),encoding='utf-8')
    (run/'concat.txt').write_text('\n'.join("file '"+p.name+"'" for p in clips),encoding='utf-8')
    out=run/'video.mp4'
    subprocess.run([ffmpeg,'-y','-v','error','-f','concat','-safe','0','-i',str(run/'concat.txt'),'-c','copy','-movflags','+faststart',str(out)],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    elapsed=round(time.monotonic()-start,2)
    (run/'render-report.json').write_text(json.dumps({'renderer':'whiteboard-paths-v6','frames':int(end[-1]),'fps':fps,'render_seconds':elapsed,'hand':bool(pencil and pencil.image is not None),'camera':camera,'source':'raster centre-line approximation','assets':list(used)},indent=2),encoding='utf-8')
    job.update(status='done',progress=100,message='فيديو الوايت بورد جاهز',url=f'/outputs/{run.name}/video.mp4',folder=str(run),
               board=f'/outputs/{run.name}/board.png',render_seconds=elapsed,clips=[f'/outputs/{run.name}/{p.name}' for p in clips])
