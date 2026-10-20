"""Read/export QA only within the isolated asset sandbox."""
from pathlib import Path
import json,subprocess,hashlib
import numpy as np
from PIL import Image,ImageDraw,ImageFont

P=Path(__file__).resolve().parents[1]
FF=Path(r'D:\withbord inmation\studio\runtime\ffmpeg.exe')
FP=FF.with_name('ffprobe.exe')

def main():
    source=P/'previews/presenter_demo.mp4'
    final=P/'previews/presenter_demo_review.mp4'
    sourceprobe=json.loads(subprocess.run([str(FP),'-v','error','-show_streams','-of','json',str(source)],capture_output=True,text=True,check=True).stdout)
    video_duration=next(s['duration'] for s in sourceprobe['streams'] if s['codec_type']=='video')
    subprocess.run([str(FF),'-y','-v','error','-i',str(source),'-c:v','copy','-af',f'loudnorm=I=-16:TP=-2:LRA=11,aresample=48000,atrim=end={video_duration}',
                    '-ar','48000','-t',video_duration,'-c:a','aac','-b:a','160k','-movflags','+faststart',str(final)],check=True)
    probe=json.loads(subprocess.run([str(FP),'-v','error','-show_streams','-show_format','-of','json',str(final)],capture_output=True,text=True,check=True).stdout)
    decode=subprocess.run([str(FF),'-v','error','-i',str(final),'-f','null','-'],capture_output=True,text=True)
    loud=subprocess.run([str(FF),'-hide_banner','-i',str(final),'-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    try:loudness=json.JSONDecoder().raw_decode(loud.stderr[loud.stderr.rfind('{'):])[0]
    except Exception:loudness={'measurement':'unavailable'}
    motions=[]
    selected=P/'rig/selected_motion_frames';selected.mkdir(exist_ok=True)
    for path in sorted((P/'motion_clips').glob('*.webp')):
        with Image.open(path) as im:
            n=im.n_frames;d=0;images=[]
            for i in range(n):
                im.seek(i);im.load();d+=im.info.get('duration',0)
                if i in [0,n//2,n-1]:
                    im.convert('RGBA').save(selected/f'{path.stem}_{i:03d}.png')
                    images.append(np.asarray(im.convert('RGBA')).astype(np.int16))
            motions.append({'file':path.name,'frames_decoded':n,'duration_ms':d,'alpha_present':im.mode=='RGBA',
                            'first_last_decoded_mean_abs_delta':float(np.abs(images[0]-images[-1]).mean()),
                            'loop_certified':False})
    protected=json.loads((P/'reports/protected_before.json').read_text())
    project=P.parents[1]
    changes=[name for name,h in protected.items() if hashlib.sha256((project/name).read_bytes()).hexdigest()!=h]
    attachments=json.loads((P/'reports/attachment_checks.json').read_text())
    v=next(s for s in probe['streams'] if s['codec_type']=='video')
    a=next(s for s in probe['streams'] if s['codec_type']=='audio')
    av_delta=abs(float(v['duration'])-float(a['duration']))
    # Deformation field Jacobian for strongest paired arm pulse; non-folding
    # is a technical condition, NOT evidence of anatomically correct movement.
    yy,xx=np.indices((840,560),dtype=np.float32);scale=560/1024
    x=xx/scale;y=yy/scale
    left=np.exp(-((x-200)/180)**2-((y-1000)/230)**2)
    right=np.exp(-((x-860)/170)**2-((y-1000)/230)**2)
    dx=(-32*left*.14+32*right*.14)*scale;dy=(-32*left-32*right)*scale
    dx_y,dx_x=np.gradient(dx);dy_y,dy_x=np.gradient(dy)
    jac=(1-dx_x)*(1-dy_y)-dx_y*dy_x
    report={'video':{'path':str(final),'full_decode_ok':decode.returncode==0,'decode_errors':decode.stderr,
        'width':v['width'],'height':v['height'],'fps':v['avg_frame_rate'],'codec':v['codec_name'],
        'video_frames':v.get('nb_frames'),'audio_codec':a['codec_name'],'duration':probe['format']['duration'],
        'av_duration_delta_seconds':av_delta,'within_one_video_frame':av_delta<=1/30,
        'loudness_measured':loudness},'motions':motions,'decoded_motion_frames':sum(m['frames_decoded'] for m in motions),
        'attachments':attachments,'isolation':{'protected_files':len(protected),'changed_files':changes},
        'deformation_test':{'minimum_sampled_jacobian':float(jac.min()),'no_fold_in_sampled_extreme':bool(jac.min()>0),
                            'anatomical_motion_verified':False},
        'visual_review':'Generated sources and 6 video stills/contact sheet inspected; full stream decoded. No claim of human real-time playback/listening review.',
        'quality_verdict':'Technical prototype passes file/decode/isolation checks. NOT approved as professional character animation.',
        'remaining':['clean articulated shoulder/elbow/wrist rig','authored think/contact/point transitions (8 planned actions incomplete)',
                     'accurate and registered English viseme set beyond three mouth groups','male brand voice (current female system voice is fixture only)',
                     'purposeful readable hand shapes and anticipation/follow-through','loop endpoint cleanup','true word-timed captions (current blocks approximate)',
                     'production review at playback speed and target display resolution']}
    (P/'reports/final_quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'decode_ok':decode.returncode==0,'frames':v.get('nb_frames'),'av_delta':av_delta,'motion_clips':len(motions),'motion_frames':report['decoded_motion_frames'],'protected_changed':changes,'input_i':loudness.get('input_i'),'input_tp':loudness.get('input_tp')},ensure_ascii=False))

if __name__=='__main__':main()
