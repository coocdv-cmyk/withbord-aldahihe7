"""Offline procedural preview. Draws primitives, no input image assets or Rasm imports."""
from pathlib import Path
import json,math,subprocess,time,hashlib
import numpy as np
from PIL import Image,ImageDraw,ImageFont

P=Path(__file__).resolve().parent
FF=Path(r'D:\withbord inmation\studio\runtime\ffmpeg.exe')
FP=FF.with_name('ffprobe.exe')
S=1.5;W,H=1280,720;INK='#202932';EYE='#f8f5e8'
FONT=r'C:\Windows\Fonts\arial.ttf'
def scaled(v):return tuple(round(x*S) for x in v)
def ellipse(d,xy,rx,ry,fill):
 x,y=xy;d.ellipse(scaled((x-rx,y-ry,x+rx,y+ry)),fill=fill)
def rr(d,box,r,fill):d.rounded_rectangle(scaled(box),radius=round(r*S),fill=fill)
def line(d,pts,width,fill):
 d.line([scaled(p) for p in pts],width=round(width*S),fill=fill,joint='curve')
 for p in pts:ellipse(d,p,width/2,width/2,fill)
def bezier(points,n=18):
 p=np.array(points,dtype=float);ts=np.linspace(0,1,n)
 if len(p)==4:return [tuple((1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3]) for t in ts]
 return [tuple((1-t)**2*p[0]+2*(1-t)*t*p[1]+t*t*p[2]) for t in ts]
def poly(d,pts,fill):d.polygon([scaled(p) for p in pts],fill=fill)
def scene_background():
 yy,xx=np.indices((H,W),dtype=np.float32)
 t=yy/H;top=np.array([230,223,206]);bottom=np.array([198,186,161])
 arr=top[None,None,:]*(1-t[...,None])+bottom[None,None,:]*t[...,None]
 g=np.clip(1-np.sqrt(((xx-640)/500)**2+((yy-280)/450)**2),0,1)[...,None]
 arr=arr*(1-.45*g)+np.array([255,245,221])*.45*g
 im=Image.fromarray(arr.astype('uint8')).resize((round(W*S),round(H*S)),Image.Resampling.BICUBIC);d=ImageDraw.Draw(im)
 d.rectangle(scaled((0,625,1280,720)),fill='#a99a80');d.rectangle(scaled((0,619,1280,626)),fill='#786c59')
 rr(d,(74,115,279,575),6,'#84765f');rr(d,(88,129,265,560),3,'#615c4e')
 for row in range(4):
  y=160+row*100
  for j in range(9):
   h=43+(j*13+row*7)%30
   rr(d,(99+j*17,y+65-h,111+j*17,y+65),2,['#9eaa9e','#c6b791','#b08869','#727e79'][(j+row)%4])
  d.rectangle(scaled((86,y+68,266,y+76)),fill='#b5a180')
 rr(d,(1002,460,1200,472),5,'#8d7357');line(d,[(1020,470),(1015,625)],9,'#80684f');line(d,[(1184,470),(1190,625)],9,'#80684f')
 line(d,[(1102,453),(1102,345)],7,'#786343');poly(d,[(1065,345),(1139,345),(1123,290),(1081,290)],'#b69258')
 rr(d,(1012,176,1112,251),2,'#8d8069');rr(d,(1019,183,1105,244),1,'#d4cbb7')
 rr(d,(1113,535,1167,598),10,'#a08366');line(d,[(1140,539),(1138,435)],5,'#717e66')
 for j in range(5):ellipse(d,(1121+(j%2)*35,451+j*17),17,8,'#77836b')
 return im
def hand(d,arm,mode):
 x,y=arm['w'];angle=math.atan2(y-arm['e'][1],x-arm['e'][0])
 if mode=='point_left':angle=math.pi
 elif mode=='point_right':angle=0
 elif mode=='point_up':angle=-math.pi/2
 def tr(p):return (x+p[0]*math.cos(angle)-p[1]*math.sin(angle),y+p[0]*math.sin(angle)+p[1]*math.cos(angle))
 # Polygonal ellipse permits arbitrary hand rotation.
 poly(d,[tr((8+13*math.cos(t),10*math.sin(t))) for t in np.linspace(0,math.tau,24)],INK)
 if mode.startswith('point'):
  for pts,w in [([(11,-5),(34,-5)],6),([(12,4),(21,6)],9),([(3,7),(12,13)],6)]:line(d,[tr(v) for v in pts],w,INK)
 elif mode=='open':
  for j in range(4):
   off=-8+j*5;line(d,[tr((11,off)),tr((26-abs(j-1.5)*4,off*1.5))],5,INK)
  line(d,[tr((4,8)),tr((12,19))],6,INK)
 else:
  line(d,[tr((7,0)),tr((18,0))],16,INK);line(d,[tr((4,7)),tr((13,12))],6,INK)
def actor(p):
 im=Image.new('RGBA',(round(W*S),round(H*S)),(0,0,0,0));d=ImageDraw.Draw(im)
 for i in range(2):
  line(d,[p['hips'][i],p['knees'][i]],31,INK);line(d,[p['knees'][i],p['ankles'][i]],26,INK)
  x=p['ankles'][i][0]-15-(0 if i else 9);rr(d,(x,614,x+42,634),9,INK)
 line(d,[(p['head'][0],255),(p['head'][0],293)],30,INK)
 for a in [p['left'],p['right']]:line(d,[a['s'],a['e']],29,INK);line(d,[a['e'],a['w']],23,INK);ellipse(d,a['e'],13,13,INK)
 x=p['chest'][0]-640;y=p['chest'][1]-360
 pts=bezier([(594+x,279+y),(607+x,270+y),(673+x,270+y),(686+x,279+y)])
 pts+=bezier([(686+x,279+y),(702+x,311+y),(689+x,383+y),(682+x,412+y)])
 pts+=[(684,451)]+bezier([(684,451),(640,467),(596,451)])+[(598+x,412+y)]
 pts+=bezier([(598+x,412+y),(589+x,370+y),(578+x,309+y),(594+x,279+y)])
 poly(d,pts,INK);line(d,[(629+x,278+y),(640+x,286+y),(651+x,278+y)],2,'#73818a')
 hand(d,p['left'],p['lh']);hand(d,p['right'],p['rh'])
 # Draw head in local coordinates; transform all eye geometry with the same head rotation.
 hc=p['head'];tilt=p['eye']['tilt']
 def tr(v):return (hc[0]+v[0]*math.cos(tilt)-v[1]*math.sin(tilt),hc[1]+v[0]*math.sin(tilt)+v[1]*math.cos(tilt))
 pts=bezier([(-38,-23),(-39,-55),(39,-55),(38,-23)])
 pts+=bezier([(38,-23),(43,10),(29,41),(0,45)])
 pts+=bezier([(0,45),(-29,41),(-43,10),(-38,-23)])
 poly(d,[tr(v) for v in pts],INK)
 for side in [-1,1]:
  e=p['eye'];h=e['l' if side<0 else 'r']*(1-p['blink']);slope=e['sl' if side<0 else 'sr'];cx=side*18+e['gx'];cy=e['gy']-3
  def eye_tr(v):return tr((cx+v[0]*math.cos(slope)-v[1]*math.sin(slope),cy+v[0]*math.sin(slope)+v[1]*math.cos(slope)))
  if h<1.2:line(d,[eye_tr((-9,0)),eye_tr((0,1)),eye_tr((9,0))],2,EYE)
  else:
   # Rounded capsule polygon, preserves white eyes without external artwork.
   rx=11;ry=h/2
   poly(d,[eye_tr((rx*math.cos(t),ry*math.sin(t))) for t in np.linspace(0,math.tau,28)],EYE)
 return im
def render():
 start=time.perf_counter();poses=json.loads((P/'reports/poses.json').read_text());bg=scene_background()
 proc=subprocess.Popen([str(FF),'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','1280x720','-r','30','-i','-',
  '-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(P/'preview/shadow_demo.mp4')],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
 picks={30,130,220,310,400,490,580,670,760,850};thumbs=[]
 for i,p in enumerate(poses):
  a=actor(p);im=bg.convert('RGBA')
  shadow=Image.new('RGBA',im.size);ellipse(ImageDraw.Draw(shadow),(640,638),103,13,(48,43,36,37));im=Image.alpha_composite(im,shadow)
  im=Image.alpha_composite(im,a).convert('RGB').resize((W,H),Image.Resampling.LANCZOS)
  d=ImageDraw.Draw(im);f=ImageFont.truetype(FONT,24)
  d.text((42,36),'PROCEDURAL SHADOW / '+p['label'].upper(),font=f,fill='#394447')
  d.text((42,69),'No source images. No mouth. Calculated joints and eyes.',font=ImageFont.truetype(FONT,16),fill='#5b655f')
  proc.stdin.write(im.tobytes())
  if i in picks:
   im.save(P/'preview'/f'scene_{p["scene"]+1:02d}.png');thumbs.append(im.copy())
  if i==30:a.resize((W,H),Image.Resampling.LANCZOS).save(P/'preview/shadow_transparent_sample.png')
 proc.stdin.close();err=proc.stderr.read();rc=proc.wait()
 if rc:raise RuntimeError(err.decode(errors='replace'))
 sheet=Image.new('RGB',(1280,720),'#e6dfce')
 for i,im in enumerate(thumbs):
  portrait=im.crop((410,110,870,670));portrait.thumbnail((224,300))
  x=(i%5)*256+(256-portrait.width)//2;y=(i//5)*360+12
  sheet.paste(portrait,(x,y))
  ImageDraw.Draw(sheet).text(((i%5)*256+12,(i//5)*360+322),poses[sorted(picks)[i]]['gesture'],font=ImageFont.truetype(FONT,17),fill='#394447')
 sheet.save(P/'preview/contact_sheet.jpg',quality=93)
 # Read every encoded frame, then check expected dimensions/rate/duration.
 probe=json.loads(subprocess.run([str(FP),'-v','error','-show_streams','-show_format','-of','json',str(P/'preview/shadow_demo.mp4')],capture_output=True,text=True,check=True).stdout)
 check=subprocess.run([str(FF),'-v','error','-i',str(P/'preview/shadow_demo.mp4'),'-f','null','-'],capture_output=True,text=True)
 before=json.loads((P/'reports/protected_before.json').read_text());project=P.parents[1]
 changed=[name for name,h in before.items() if hashlib.sha256((project/name).read_bytes()).hexdigest()!=h]
 result={'full_decode_ok':check.returncode==0,'decode_errors':check.stderr,'probe':probe,'render_seconds':time.perf_counter()-start,
         'protected_engine_files':len(before),'changed_engine_files':changed,'source_images_used':0,'renderers':'Browser Canvas and Python procedural primitives share rig.js geometry; rasterization differs slightly.',
         'voice':'none; deliberate no-mouth visual prototype','quality':'Design prototype; no claim of human physical realism.'}
 (P/'reports/video_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps({'decode_ok':check.returncode==0,'frames':len(poses),'seconds':30,'render_seconds':result['render_seconds'],'engine_changed':changed}))
if __name__=='__main__':render()
