import sys,json,subprocess
from pathlib import Path
B=Path(__file__).resolve().parent
R=B.parent/'rasm-pro'
sys.path.insert(0,str(B/'snapshot'))
import engine.core.paths as p
p.FONTS=R/'assets/fonts';p.CACHE=B/'cache';p.LOGS=B/'logs'
from engine.render.validate import validate_video
from engine.strokes.text_paths import text_to_strokes,find_font
out={}
for name,size,fps,seconds in [('english-three-styles',(1280,720),24,729/24),('ten-minute-reduced-load',(640,360),2,600)]:
 f=B/(name+'.mp4')
 v=validate_video(f,expect_size=size,expect_fps=fps,expect_audio=False,expect_duration_sec=seconds)
 dec=subprocess.run([str(B.parent/'studio/runtime/ffmpeg.exe'),'-v','error','-i',str(f),'-f','null','-'],capture_output=True)
 v['full_decode_returncode']=dec.returncode;v['full_decode_errors']=dec.stderr.decode('utf-8','replace')
 e=json.loads((B/(name+'.sfx.json')).read_text())['events']
 v['events_after_video']=sum(float(x['t'])>seconds for x in e)
 v['max_event_time']=max(float(x['t']) for x in e)
 out[name]=v
d=text_to_strokes('Read the sequence',find_font('cairo'),100,rtl=False)
words=[]
for w in d.stats['words']:
 pts=[pt for s in d.strokes[w['start']:w['end']] for pt in s.points]
 words.append({'text':w['text'],'min_x':min(pt[0] for pt in pts),'max_x':max(pt[0] for pt in pts)})
out['english_word_geometry']={'input':'Read the sequence','rtl':False,'words_in_logical_order':words,'visual_left_to_right':[w['text'] for w in sorted(words,key=lambda w:w['min_x'])]}
out['sfx_memory_calculation']=[{'minutes':m,'float32_buffer_bytes':int((m*60+.5)*48000)*4,'pcm16_bytes':int((m*60+.5)*48000)*2,'frames_at_24fps':m*60*24} for m in [10,20,60,120]]
(B/'verified-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False))
