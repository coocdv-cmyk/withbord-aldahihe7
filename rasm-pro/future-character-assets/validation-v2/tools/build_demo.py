"""Isolated asset QA and 2D deformation prototype. No Rasm imports or integration."""
from pathlib import Path
import json, hashlib, math, subprocess, time, wave, bisect
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT.parent
PROJECT=LIB.parent
FF=Path(r'D:\withbord inmation\studio\runtime\ffmpeg.exe')
FP=FF.with_name('ffprobe.exe')
FPS=30
W,H=1280,720

def dump(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def font(n):
    return ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',n)

def audit():
    rows=[]
    manifest=json.loads((LIB/'manifest.json').read_text(encoding='utf-8'))
    for item in manifest['assets']:
        p=LIB/item['path']
        with Image.open(p) as im:
            im.load()
            row={'path':item['path'],'decode_ok':True,'size':list(im.size),'mode':im.mode,
                 'hash_matches_v1_manifest':hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']}
            if im.mode=='RGBA':
                a=np.asarray(im.getchannel('A'))
                row.update(alpha_min=int(a.min()),alpha_max=int(a.max()),transparent_fraction=float((a==0).mean()),
                           low_alpha_fraction=float(((a>0)&(a<16)).mean()))
            rows.append(row)
    dump(ROOT/'reports'/'original_asset_audit.json',{'files':rows,
        'visual_findings':{'mouth_sources_12':'Reject for direct attachment: realistic mouth style mismatches illustrated head; FV/L/TH unvalidated.',
        'hands_12':'Reference only: no matching wrist registration; do not swap directly.',
        'body_poses_12':'Reference only: different body/head proportions and two right-pointing poses.',
        'blink_08':'Not playback-ready: head and gaze drift.',
        'explain_08':'Not playback-ready: torso/hand registration and endpoints drift.',
        'hair_04':'Not attachable to baked-hair head without a clean head layer.'}})

def patch_on(base,source,mask):
    # Video-rig preparation: retain a single body and copy only local generated facial edits.
    return (base*(1-mask[...,None])+source*mask[...,None]).astype(np.uint8)

def ellipse_mask(shape,center,radii):
    yy,xx=np.indices(shape,dtype=np.float32)
    d=((xx-center[0])/radii[0])**2+((yy-center[1])/radii[1])**2
    return np.clip((1-d)*5,0,1)

def prepare():
    base=np.array(Image.open(ROOT/'sources'/'presenter_explain.png').convert('RGBA'))
    hh,ww=base.shape[:2]
    mouthmask=ellipse_mask((hh,ww),(524,322),(61,22))
    eyemask=np.maximum(ellipse_mask((hh,ww),(476,225),(39,18)),ellipse_mask((hh,ww),(580,233),(40,18)))
    variants=[]
    for name in ['presenter_explain','mouth_open_source','mouth_round_source']:
        src=np.array(Image.open(ROOT/'sources'/f'{name}.png').convert('RGBA'))
        if src.shape!=base.shape:raise ValueError('Source size mismatch')
        variants.append(patch_on(base,src,mouthmask) if name!='presenter_explain' else base.copy())
    blink=np.array(Image.open(ROOT/'sources'/'blink_source.png').convert('RGBA'))
    diff=np.max(np.abs(variants[1].astype(int)-base.astype(int)),axis=2)
    outside=mouthmask==0
    dump(ROOT/'reports'/'attachment_checks.json',{
        'master_size':[ww,hh],'mouth_region':[449,283,599,359],
        'body_pixels_changed_by_open_mouth_patch':int(np.count_nonzero(diff[outside])),
        'hand_replacement':'None: hands use original same-body pixels, deformed continuously.',
        'head_replacement':'None: head uses original same-body pixels.',
        'phoneme_groups':3,'phoneme_accuracy_claim':'No: coarse closed/open/round mapping only.',
        'mouth_color_and_identity':'Local generated edits, feathered attachment; visually reviewed, not a perfect registered viseme rig.'})
    for j,a in enumerate(variants):
        Image.fromarray(a).save(ROOT/'rig'/f'master_mouth_{j}.png')
    Image.fromarray((mouthmask*255).astype('uint8')).save(ROOT/'rig'/'mouth_attachment_mask.png')
    Image.fromarray((eyemask*255).astype('uint8')).save(ROOT/'rig'/'eye_attachment_mask.png')
    # Export separate patches for the later rig; keep world-space rectangle metadata.
    for j,a in enumerate(variants):
        region=a[283:359,449:599].copy()
        region[...,3]=(mouthmask[283:359,449:599]*255).astype('uint8')
        Image.fromarray(region).save(ROOT/'rig'/f'mouth_patch_{j}.png')
    bpatch=blink[200:256,432:624].copy()
    bpatch[...,3]=(eyemask[200:256,432:624]*255).astype('uint8')
    Image.fromarray(bpatch).save(ROOT/'rig'/'blink_patch.png')
    dump(ROOT/'rig'/'attachments.json',{'mouth':{'rect':[449,283,599,359],'pivot':[524,321]},'blink':{'rect':[432,200,624,256]},'master_size':[ww,hh],'rig_type':'single-image localized deformation, not articulated skeletal rig'})
    scale=560/ww
    size=(560,round(hh*scale))
    tex=[]
    for a in variants:
        a=cv2.resize(a,size,interpolation=cv2.INTER_AREA).astype(np.float32)/255
        alpha=a[...,3:4]
        alpha=np.where(alpha<4/255,0,np.minimum(alpha/(253/255),1))
        a[...,3:4]=alpha
        a[...,:3]*=alpha
        tex.append(a)
    blinkbase=patch_on(base,blink,eyemask)
    closed=cv2.resize(blinkbase,size,interpolation=cv2.INTER_AREA).astype(np.float32)/255
    ba=closed[...,3:4]
    ba=np.where(ba<4/255,0,np.minimum(ba/(253/255),1))
    closed[...,3:4]=ba;closed[...,:3]*=ba
    # Only eyelid delta is added; mouth independently controls speaking.
    blinkdelta=closed-tex[0]
    return tex,blinkdelta,scale

def smooth(x):
    x=max(0.,min(1.,x));return x*x*(3-2*x)

def pulse(t,start,end):
    if t<start or t>end:return 0.
    r=(t-start)/(end-start)
    return smooth(r/.28)*smooth((1-r)/.28)

class Actor:
    def __init__(self,tex,blinkdelta,scale):
        self.tex=tex;self.blinkdelta=blinkdelta;self.scale=scale
        self.yy,self.xx=np.indices(tex[0].shape[:2],dtype=np.float32)
        x=self.xx/scale;y=self.yy/scale
        self.head=np.clip((540-y)/160,0,1)
        self.left=np.exp(-((x-200)/180)**2-((y-1000)/230)**2)
        self.right=np.exp(-((x-860)/170)**2-((y-1000)/230)**2)
        self.torso=np.exp(-((x-520)/300)**2-((y-700)/400)**2)
        self.hair=np.exp(-((x-460)/160)**2-((y-80)/95)**2)
        self.gaze_l=ellipse_mask(x.shape,(476*scale,225*scale),(19*scale,10*scale))
        self.gaze_r=ellipse_mask(x.shape,(580*scale,233*scale),(19*scale,10*scale))

    def frame(self,t,mouth=(0,0.),blink=0.,left=0.,right=0.,nod=0.,tilt=0.,lean=0.,brow=0.,gaze=0.,hair=0.):
        group,amount=mouth
        image=self.tex[0]*(1-amount)+self.tex[group]*amount
        image=np.clip(image+self.blinkdelta*blink,0,1)
        s=self.scale
        theta=tilt*math.pi/180
        # Small deformation fields: useful for subtle motion, NOT full anatomical articulation.
        dx=self.head*((self.yy-360*s)*theta+lean*s)
        dy=self.head*(nod*s-(self.xx-520*s)*theta)
        dy+=self.left*left*s+self.right*right*s
        dx+=self.left*left*.14*s-self.right*right*.14*s
        breath=1.2*math.sin(2*math.pi*t/4)
        dy+=self.torso*breath*s
        dy+=self.hair*hair*s
        eyeweight=self.gaze_l+self.gaze_r
        dx+=eyeweight*gaze*s
        # Brow field kept above the glasses, low amplitude.
        browfield=np.exp(-((self.xx-520*s)/(135*s))**2-((self.yy-190*s)/(16*s))**2)
        dy+=browfield*brow*s
        mx=(self.xx-dx).astype(np.float32);my=(self.yy-dy).astype(np.float32)
        result=cv2.remap(image,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        return result

def speech_data():
    events=json.loads((ROOT/'audio'/'visemes.json').read_text(encoding='utf-8-sig'))
    with wave.open(str(ROOT/'audio'/'narration.wav')) as w:
        sr=w.getframerate();data=w.readframes(w.getnframes());ch=w.getnchannels();sw=w.getsampwidth()
    if sw!=2:raise ValueError('Expected SAPI PCM16')
    audio=np.frombuffer(data,dtype='<i2').astype(np.float32)/32768
    if ch>1:audio=audio.reshape(-1,ch).mean(axis=1)
    # System.Speech AudioPosition from this installed voice disagrees with the
    # produced WAV; sequential event durations sum to the PCM duration instead.
    raw_end=events[-1]['t']+events[-1]['duration']
    cursor=0.
    for e in events:
        e['raw_audio_position']=e['t'];e['t']=cursor;cursor+=e['duration']
    error=cursor-len(audio)/sr
    if abs(error)>.02:raise ValueError('Viseme duration sum does not match audio')
    dump(ROOT/'audio'/'visemes_corrected.json',events)
    dump(ROOT/'reports'/'speech_timing_check.json',{'raw_event_end':raw_end,'pcm_duration':len(audio)/sr,
        'duration_sum':cursor,'duration_error_seconds':error,'method':'cumulative SAPI event durations; raw AudioPosition rejected',
        'phonetic_alignment_verified_by_listener':False})
    return events,audio,sr

def mouth_at(t,events,audio,sr):
    i=bisect.bisect_right([e['t'] for e in events],t)-1
    event=events[max(0,i)]
    id=event['id']
    seg=audio[max(0,int((t-.015)*sr)):min(len(audio),int((t+.025)*sr))]
    rms=math.sqrt(float(np.mean(seg*seg))) if len(seg) else 0
    if rms<.006 or id in [0,21]:return (0,0.)
    group=2 if id in [3,7,8,9,10,13] else 1
    attack=smooth((t-event['t'])/.045)
    amount=min(.95,max(.35,rms*10))*attack
    return group,amount

def composite(actor,bg,caption=None,labels=None):
    frame=bg.copy()
    a=actor;ah,aw=a.shape[:2];x=360;y=38
    top=max(0,y);bottom=min(H,y+ah)
    roi=frame[top:bottom,x:x+aw].astype(np.float32)/255
    part=a[top-y:bottom-y]
    frame[top:bottom,x:x+aw]=np.clip((part[...,:3]+roi*(1-part[...,3:4]))*255,0,255).astype('uint8')
    im=Image.fromarray(frame)
    draw=ImageDraw.Draw(im,'RGBA')
    if labels:
        for text,side,opacity in labels:
            lx=52 if side=='left' else 960
            draw.rounded_rectangle((lx,240,lx+260,306),radius=8,fill=(245,235,214,int(235*opacity)))
            draw.text((lx+18,259),text,font=font(22),fill=(30,43,43,int(255*opacity)))
    if caption:
        draw.rounded_rectangle((95,650,1185,708),radius=10,fill=(12,24,28,225))
        box=draw.textbbox((0,0),caption,font=font(24))
        draw.text(((W-(box[2]-box[0]))/2,666),caption,font=font(24),fill=(255,249,235,255))
    return np.asarray(im)

def writer(path,size,fps,audio=None):
    cmd=[str(FF),'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{size[0]}x{size[1]}','-r',str(fps),'-i','-']
    if audio:cmd+=['-i',str(audio)]
    cmd+=['-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p']
    if audio:cmd+=['-c:a','aac','-b:a','160k','-shortest']
    cmd+=['-movflags','+faststart',str(path)]
    return subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)

def close(p):
    p.stdin.close();err=p.stderr.read();rc=p.wait()
    if rc:raise RuntimeError(err.decode(errors='replace'))

def verify(path):
    p=subprocess.run([str(FP),'-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True)
    data=json.loads(p.stdout)
    d=subprocess.run([str(FF),'-v','error','-i',str(path),'-f','null','-'],capture_output=True,text=True)
    return {'probe':data,'full_decode_ok':d.returncode==0,'decode_stderr':d.stderr}

MOTIONS=[
 ('idle_breath',120,'breathing'),('weight_settle',90,'weight'),('blink',8,'blink'),('double_blink',18,'double'),
 ('gaze_left',30,'gaze_l'),('gaze_right',30,'gaze_r'),('brow_curious',30,'brow'),('brow_skeptical',30,'brow_down'),
 ('nod_yes',36,'nod'),('head_no',42,'no'),('head_tilt',36,'tilt'),('explain_right',48,'left'),
 ('explain_left',48,'right'),('welcome',60,'both'),('compare',72,'compare'),('shrug',48,'shrug'),
 ('small_concept',48,'small'),('surprise',30,'surprise'),('reassure',48,'reassure'),('hair_settle',36,'hair')]

def motion_params(kind,t,dur):
    env=pulse(t,0,dur)
    d={}
    if kind=='weight':d={'lean':5*env,'tilt':.5*env}
    elif kind=='blink':d={'blink':math.sin(math.pi*t/dur)**2}
    elif kind=='double':d={'blink':max(pulse(t,.02,.23),pulse(t,.31,.53))}
    elif kind in ['gaze_l','gaze_r']:d={'gaze':(-2 if kind=='gaze_l' else 2)*env}
    elif kind in ['brow','brow_down']:d={'brow':(-2 if kind=='brow' else 1.5)*env}
    elif kind=='nod':d={'nod':6*math.sin(2*math.pi*t/dur)*env}
    elif kind=='no':d={'lean':6*math.sin(2*math.pi*t/dur)*env}
    elif kind=='tilt':d={'tilt':1.7*env}
    elif kind=='left':d={'left':-32*env,'tilt':-.5*env}
    elif kind=='right':d={'right':-32*env,'tilt':.5*env}
    elif kind=='both':d={'left':-24*env,'right':-24*env}
    elif kind=='compare':d={'left':-28*pulse(t,.1,dur*.55),'right':-28*pulse(t,dur*.45,dur-.1)}
    elif kind=='shrug':d={'left':-18*env,'right':-18*env,'nod':-2*env}
    elif kind=='small':d={'left':-10*env,'right':-10*env}
    elif kind=='surprise':d={'brow':-3*env,'nod':-2*env}
    elif kind=='reassure':d={'nod':3*env,'tilt':-.8*env}
    elif kind=='hair':d={'hair':2.5*math.sin(2*math.pi*t/dur)*env}
    return d

def render(export_motions=True):
    start=time.perf_counter();audit()
    tex,blinkdelta,scale=prepare();actor=Actor(tex,blinkdelta,scale)
    bg=np.array(Image.open(LIB/'backgrounds'/'studio_empty.png').convert('RGB').resize((W,H),Image.Resampling.LANCZOS))
    events,audio,sr=speech_data();duration=len(audio)/sr
    sentences=['A convincing story can feel like proof.','But confidence and evidence are different things.',
               'Imagine two explanations. One sounds impressive.','The other can be checked.',
               'Before we accept a claim, ask what would prove it wrong.','A good question becomes a better explanation.']
    # Caption blocks are approximate editorial cues; SAPI events drive mouth timing.
    bounds=np.array([0,.16,.36,.54,.65,.87,1])*duration
    p=writer(ROOT/'previews'/'presenter_demo.mp4',(W,H),FPS,ROOT/'audio'/'narration.wav')
    picks={int(duration*f*FPS) for f in [.04,.22,.43,.57,.75,.93]}
    metrics=[];prev=None
    for f in range(math.ceil(duration*FPS)):
        t=f/FPS;r=t/duration
        left=-26*pulse(r,.02,.16)-28*pulse(r,.38,.52)
        right=-26*pulse(r,.19,.34)-28*pulse(r,.53,.65)
        both=pulse(r,.69,.83)
        params={'left':left-15*both,'right':right-15*both,
                'tilt':-.8*pulse(r,.17,.30)+.7*pulse(r,.71,.85),
                'nod':3*pulse(r,.88,.97),'brow':-1.5*pulse(r,.68,.81)}
        blink=max([pulse(t,s,s+.23) for s in [2.3,6.8,11.4,16.2,21.6,26.0]])
        a=actor.frame(t,mouth=mouth_at(t,events,audio,sr),blink=blink,**params)
        cap=sentences[min(len(sentences)-1,max(0,bisect.bisect_right(bounds,t)-1))]
        labels=[]
        if .18<r<.36:labels=[('CONFIDENCE','left',1),('EVIDENCE','right',1)]
        elif .38<r<.65:labels=[('SOUNDS GOOD','left',1),('CAN BE CHECKED','right',1)]
        frame=composite(a,bg,cap,labels)
        p.stdin.write(frame.tobytes())
        if prev is not None:metrics.append(float(np.abs(frame.astype(np.int16)-prev).mean()))
        prev=frame.astype(np.int16)
        if f in picks:Image.fromarray(frame).save(ROOT/'previews'/f'frame_{f:04d}.png')
    close(p)
    dump(ROOT/'reports'/'demo_validation.json',{'duration_audio':duration,'fps':FPS,'frames_requested':math.ceil(duration*FPS),
        'speech_voice':'Microsoft Zira Desktop (female system voice; timing fixture, not final host voice)',
        'lip_method':'Cumulative SAPI viseme durations (raw AudioPosition rejected) + audio RMS silence gate; 3 mouth groups, NOT full phoneme lip sync.',
        'gestures':'Authored editorial cues; local deformation of one image, not realistic articulated motion.',
        'mean_abs_frame_difference':{'mean':float(np.mean(metrics)),'max':float(max(metrics))},
        'render_seconds':time.perf_counter()-start,'validation':verify(ROOT/'previews'/'presenter_demo.mp4')})
    print('Demo rendered and decoded',round(duration,2),'seconds',flush=True)
    if not export_motions:
        return
    # Export actual continuous transparent WebP clips for supported low-amplitude motions.
    contact=[];motionrows=[]
    for id,n,kind in MOTIONS:
        frames=[];dur=(n-1)/FPS
        for i in range(n):
            a=actor.frame(i/FPS,**motion_params(kind,i/FPS,dur))
            alpha=a[...,3:4]
            rgb=np.divide(a[...,:3],np.maximum(alpha,1e-6))
            rgba=np.concatenate([np.clip(rgb,0,1),alpha],axis=2)
            frames.append(Image.fromarray((rgba*255).astype('uint8')))
        frames[0].save(ROOT/'motion_clips'/f'{id}.webp',save_all=True,append_images=frames[1:],duration=[33 if i%3!=2 else 34 for i in range(n)],loop=0,quality=85,method=3,minimize_size=False)
        first=np.array(frames[0]);last=np.array(frames[-1]);endpoint=float(np.abs(first.astype(np.int16)-last.astype(np.int16)).mean())
        contact.append((id,frames[n//2].copy()))
        with Image.open(ROOT/'motion_clips'/f'{id}.webp') as test:
            actual=test.n_frames
            for j in range(actual):test.seek(j);test.load()
        motionrows.append({'id':id,'requested_frames':n,'decoded_frames':actual,'duration_target':n/FPS,'endpoint_mean_abs_delta':endpoint,'status':'prototype_continuous_2D_deformation_not_final_anatomical_animation'})
        print('Motion',id,n,'frames',flush=True)
    sheet=Image.new('RGB',(1200,math.ceil(len(contact)/5)*285),(234,230,219))
    draw=ImageDraw.Draw(sheet)
    for j,(id,im) in enumerate(contact):
        im.thumbnail((210,250));x=j%5*240+(240-im.width)//2;y=j//5*285
        sheet.paste(im,(x,y),im)
        draw.text((j%5*240+8,y+257),id,font=font(16),fill=(20,30,30))
    sheet.save(ROOT/'previews'/'motion_contact_sheet.jpg',quality=92)
    remaining=['emphasize_index','think_enter','think_hold','think_exit','sincere_hand_chest','point_left','point_right','return_neutral_from_arbitrary_pose']
    dump(ROOT/'reports'/'motion_inventory.json',{'exported':motionrows,'not_completed':remaining,
        'reason':'These need clean articulated arms and new contact/point poses; warping open palms into them would fake anatomy.',
        'caution':'WebP duration rounding yields approximately 30fps. These are intentionally subtle prototypes, not final realistic body acting.'})
    before=json.loads((ROOT/'reports'/'protected_before.json').read_text())
    changed=[p for p,h in before.items() if hashlib.sha256((PROJECT/p).read_bytes()).hexdigest()!=h]
    dump(ROOT/'reports'/'isolation_check.json',{'protected_files':len(before),'changed_files':changed,'all_output_under':str(ROOT),'rasm_imports':False})
    print('DONE; protected changed',changed,flush=True)

if __name__=='__main__':render()
