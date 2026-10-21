/* Shadow Motion v4: hierarchical 3D joints, orthographic 2D presentation.
 * Independent procedural study; not motion capture or a full human simulation. */
(function(root){
'use strict';
const W=1280,H=720,FPS=30,CX=640,FLOOR=652;
const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
const mix=(a,b,t)=>a+(b-a)*t;
const smooth=x=>{x=clamp(x);return x*x*x*(10+x*(-15+6*x));};
const add=(a,b)=>a.map((v,i)=>v+b[i]);
const sub=(a,b)=>a.map((v,i)=>v-b[i]);
const mul=(a,n)=>a.map(v=>v*n);
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const norm=a=>Math.hypot(...a);
const unit=a=>mul(a,1/Math.max(norm(a),1e-9));
const I=[1,0,0,0,1,0,0,0,1];
function mat(a,b){let c=Array(9).fill(0);for(let r=0;r<3;r++)for(let k=0;k<3;k++)for(let j=0;j<3;j++)c[r*3+j]+=a[r*3+k]*b[k*3+j];return c;}
const mv=(m,v)=>[dot(m.slice(0,3),v),dot(m.slice(3,6),v),dot(m.slice(6,9),v)];
const rx=a=>[1,0,0,0,Math.cos(a),-Math.sin(a),0,Math.sin(a),Math.cos(a)];
const ry=a=>[Math.cos(a),0,Math.sin(a),0,1,0,-Math.sin(a),0,Math.cos(a)];
const rz=a=>[Math.cos(a),-Math.sin(a),0,Math.sin(a),Math.cos(a),0,0,0,1];
const project=p=>[p[0],p[1]];
const LEN={upper:98,fore:90,thigh:114,shin:112};
// Limits are conservative authoring bounds for this character, not medical ranges.
const LIMITS=[[-.12,1.5],[-.25,.7],[-1.45,1.45],[.08,2.72],[-1.5,1.5],[-.35,.35],[-.28,.28]];
// [shoulder outward elevation, forward flexion, humeral twist,
//  elbow flexion, forearm pronation, wrist flexion, wrist deviation]
const REST=[.07,.035,0,.17,.28,.025,0];
const arm=(q,hand='relax')=>({q,hand});
const idle=()=>arm(REST);
const GESTURES={
 idle:{L:idle(),R:idle(),lean:0},
 explain_l:{L:arm([.16,.20,-.92,1.10,.95,.05,-.05],'open'),R:idle(),lean:-.18},
 explain_r:{L:idle(),R:arm([.16,.20,.92,1.10,-.95,.05,.05],'open'),lean:.18},
 welcome:{L:arm([.29,.22,-1.05,1.18,1.0,.03,-.03],'palmup'),R:arm([.29,.22,1.05,1.18,-1.0,.03,.03],'palmup'),lean:0},
 compare:{L:arm([.14,.20,-1.05,1.20,.95,.04,-.03],'palmup'),R:arm([.14,.20,1.05,1.20,-.95,.04,.03],'palmup'),lean:0,alternate:true},
 question:{L:arm([.13,.23,-.83,1.28,1.05,.04,0],'palmup'),R:arm([.13,.23,.83,1.28,-1.05,.04,0],'palmup'),lean:-.1},
 point_l:{L:arm([1.24,.07,-.24,.36,.06,0,0],'point'),R:idle(),lean:-.22,look:-.55},
 point_r:{L:idle(),R:arm([1.24,.07,.24,.36,-.06,0,0],'point'),lean:.22,look:.55},
 emphasize:{L:idle(),R:arm([.38,.32,0,2.58,.12,0,0],'pointup'),lean:.06},
 chest_explain:{L:arm([.16,.20,-.92,1.05,.70,.05,-.05],'palmup'),R:arm([.10,.24,-.38,1.72,-.3,.02,0],'open'),lean:.04},
 think:{L:idle(),R:arm([.28,.50,-.6,2.65,.12,.05,0],'pinch'),lean:.05,look:-.15},
 count_fingers:{L:idle(),R:arm([.40,.27,.12,2.5,.15,0,0],'count2'),lean:.05},
 mind_blown:{L:arm([.62,.4,.15,2.6,.10,0,0],'open'),R:arm([.62,.4,-.15,2.6,-.10,0,0],'open'),lean:0},
 heart:{L:idle(),R:arm([.09,.27,-1.20,2.12,1.05,.04,0],'open'),lean:-.05},
 listening:{L:idle(),R:idle(),lean:0}
};
// Thumb,index,middle,ring,pinky. These are rotations, never changing bone lengths.
const HANDS={
 relax:{c:[.32,.28,.35,.43,.49],sp:.08},open:{c:[.16,.08,.10,.13,.17],sp:.17},
 palmup:{c:[.20,.14,.18,.23,.29],sp:.12},point:{c:[.55,.03,.94,.97,.98],sp:.035},
 pointup:{c:[.55,.03,.94,.97,.98],sp:.035},pinch:{c:[.72,.70,.42,.46,.50],sp:.05},
 count2:{c:[.64,.03,.05,.94,.97],sp:.15},fist:{c:[.85,.96,.97,.98,.98],sp:.01}
};
// [aperture L/R, brow y L/R, brow angle L/R, gaze x/y, smile]
const EXPRESSIONS={
 neutral:[1,1,0,0,0,0,0,0,0],curious:[1.1,1,-3,-1,-.06,0,.12,-.08,.03],
 thinking:[.87,.87,-1,-2,0,.04,-.35,-.24,0],skeptical:[.82,1.05,2,-4,.1,-.12,0,0,-.02],
 surprised:[1.3,1.3,-6,-6,0,0,0,-.05,0],concerned:[.91,.91,-2,-2,-.15,.15,0,.15,-.13],
 serious:[.9,.9,1.4,1.4,.1,-.1,0,0,-.02],pleased:[.93,.93,-2,-2,0,0,0,0,.45],
 unsure:[.92,1.04,-1,-3,-.04,.06,.2,0,-.025],relieved:[.87,.87,0,0,0,0,0,.08,.16],
 excited:[1.17,1.17,-4,-4,0,0,0,0,.52]
};
const VISEMES={X:[0,.50,0],M:[0,.40,0],C:[.20,.58,0],A:[.65,.62,0],E:[.32,.88,0],I:[.22,.88,0],O:[.48,.24,.9],U:[.25,.12,.95],F:[.10,.65,.1]};
class Spring{
 constructor(x,w=10){this.x=x.slice();this.v=x.map(()=>0);this.w=w;}
 step(dt,target){const w=this.w,e=Math.exp(-w*dt);for(let i=0;i<this.x.length;i++){
  const d=this.x[i]-target[i],j=(this.v[i]+w*d)*dt;
  this.x[i]=target[i]+(d+j)*e;this.v[i]=(this.v[i]-w*j)*e;
 }}
}
function envelope(t,d){
 if(!Number.isFinite(t)||!Number.isFinite(d)||d<=0||t<0||t>=d)return 0;
 const a=Math.min(.72,d*.30),b=Math.min(.82,d*.32);
 return t<a?smooth(t/a):t>d-b?1-smooth((t-(d-b))/b):1;
}
const FINGER_LENGTHS=[[11,8,6],[12,8,6],[13,9,7],[12,8,6],[10,7,5]];
function handGeom(w,rot,curls,spread,side){
 const mirror=-side,at=p=>add(w,mv(rot,p));
 const palm=[[-10,-2,0],[-12,7,0],[-11,22,0],[-6,26,0],[6,26,0],[11,22,0],[12,7,0],[10,-2,0]].map(at);
 const fingers=[];const xpos=[0,9,3,-4,-10];
 for(let f=1;f<=4;f++){
  const c=clamp(curls[f]),base=[xpos[f]*mirror,24,0];let p=base.slice(),r=rz(-mirror*(2.3-f)*spread);
  const pts3=[at(p)];
  for(let j=0;j<3;j++){r=mat(r,rx(c*[1.25,1.45,.75][j]));p=add(p,mv(r,[0,FINGER_LENGTHS[f][j],0]));pts3.push(at(p));}
  const wd=[f===4?4.3:5.8,f===4?3.9:5.1,4.2,3.2];
  fingers.push({pts:pts3.map(project),pts3,w:wd,thumb:false,cum:c,lengths:FINGER_LENGTHS[f]});
 }
 // Thumb opposition: a separate saddle direction and two flexion joints.
 let p=[11*mirror,5,0],r=mat(rz(-mirror*(.75-.2*curls[0])),ry(mirror*.38*curls[0]));
 const pts3=[at(p)];for(let j=0;j<3;j++){r=mat(r,rx(curls[0]*[.35,.75,.58][j]));p=add(p,mv(r,[0,FINGER_LENGTHS[0][j],0]));pts3.push(at(p));}
 fingers.push({pts:pts3.map(project),pts3,w:[7,6,5,3.8],thumb:true,cum:curls[0],lengths:FINGER_LENGTHS[0]});
 return {palm:palm.map(project),palm3:palm,fingers,normal:mv(rot,[0,0,1]),depth:w[2]};
}
function armPose(s,q,curls,spread,side,bodyRot){
 const sh=mat(bodyRot,mat(rz(-side*q[0]),mat(rx(q[1]),ry(q[2]))));
 const e=add(s,mv(sh,[0,LEN.upper,0]));const foreRot=mat(sh,rx(q[3]));
 const w=add(e,mv(foreRot,[0,LEN.fore,0]));
 const palmRot=mat(foreRot,mat(ry(q[4]),mat(rx(q[5]),rz(q[6]))));
 return {s:project(s),e:project(e),w:project(w),s3:s,e3:e,w3:w,l1:LEN.upper,l2:LEN.fore,clamped:false,
  angles:q.slice(),hand:handGeom(w,palmRot,curls,spread,side),handAngle:Math.atan2(w[1]-e[1],w[0]-e[0]),depth:(s[2]+e[2]+w[2])/3};
}
function legPose(hip,foot){
 const v=sub(foot,hip),raw=norm(v),d=clamp(raw,Math.abs(LEN.thigh-LEN.shin)+.01,LEN.thigh+LEN.shin-.01),u=unit(v);
 let pole=unit(sub([0,0,1],mul(u,u[2])));const a=(LEN.thigh**2-LEN.shin**2+d*d)/(2*d),h=Math.sqrt(Math.max(0,LEN.thigh**2-a*a));
 const knee=add(add(hip,mul(u,a)),mul(pole,h));const ank=add(hip,mul(u,d));
 return {s:project(hip),e:project(knee),w:project(ank),s3:hip,e3:knee,w3:ank,foot:[foot[0],FLOOR],clamped:Math.abs(raw-d)>.001};
}
function createPerformer(){
 const S={t:0,arms:[new Spring(REST,9.5),new Spring(REST,9.5)],
  fingers:[new Spring(HANDS.relax.c,9),new Spring(HANDS.relax.c,9)],spreads:[new Spring([.08],8),new Spring([.08],8)],
  body:new Spring([0,0,0,0],6),expr:new Spring(EXPRESSIONS.neutral,8),mouth:new Spring(VISEMES.X,8),
  energy:new Spring([0],5),beatPulse:0,lastBeat:-99,gesture:'idle',gestureGain:0,hand:['relax','relax']};
 function integrate(dt,inp){
  const g=GESTURES[inp.gesture]||GESTURES.idle;
  const intensity=clamp(Number.isFinite(inp.intensity)?inp.intensity:1,0,1.15);
  const gain=inp.gesture==='idle'?0:envelope(inp.cueT,inp.cueDur)*intensity;
  const spoken=clamp(Number.isFinite(inp.energy)?inp.energy:inp.mouth?inp.mouth[0]*.35:0);
  S.energy.step(dt,[spoken]);S.beatPulse*=Math.exp(-dt/0.19);S.gesture=inp.gesture||'idle';S.gestureGain=gain;
  for(let i=0;i<2;i++){
   const side=i?1:-1,spec=i?g.R:g.L;
   const goal=REST.map((v,j)=>mix(v,spec.q[j],gain));
   // Small purposeful emphasis; no velocity kicks or continuous wrist noise.
   if(gain>.1){goal[3]+=S.beatPulse*.055*gain;
    if(g.alternate)goal[3]+=.08*gain*Math.sin(Math.PI*2*clamp((inp.cueT-.6)/2.2)+i*Math.PI);
   }
   LIMITS.forEach(([a,b],j)=>goal[j]=clamp(goal[j],a,b));
   S.arms[i].step(dt,goal);
   const hp=HANDS[spec.hand]||HANDS.relax;S.hand[i]=gain>.01?spec.hand:'relax';
   const hg=smooth(clamp(gain/.85));
   S.fingers[i].step(dt,HANDS.relax.c.map((v,j)=>mix(v,hp.c[j],hg)));
   S.spreads[i].step(dt,[mix(.08,hp.sp,hg)]);
  }
  const lean=(g.lean||0)*gain;
  S.body.step(dt,[lean*.055,lean*8,(g.look||0)*gain*.12,S.beatPulse*.045+spoken*.018]);
  let ex=(EXPRESSIONS[inp.expr]||EXPRESSIONS.neutral).slice();
  ex[2]-=S.beatPulse*.65;ex[3]-=S.beatPulse*.65;
  ex[6]+=g.look?g.look*gain*.35:0;
  S.expr.step(dt,ex);
  const m=Array.isArray(inp.mouth)&&inp.mouth.length===3?inp.mouth:VISEMES.X;
  S.mouth.step(dt,m.map((v,i)=>clamp(Number.isFinite(v)?v:VISEMES.X[i])));
  S.t+=dt;
 }
 function step(dt,inp={}){
  if(!Number.isFinite(dt)||dt<0)throw Error('dt must be finite and nonnegative');
  if(dt>2)throw Error('Use timeline reconstruction for gaps over two seconds');
  const n=Math.max(1,Math.ceil(dt*120));for(let i=0;i<n;i++)integrate(dt/n,inp);
 }
 function beat(s=.6){if(S.t-S.lastBeat<.36)return;S.lastBeat=S.t;S.beatPulse=Math.max(S.beatPulse,clamp(s)*.7);}
 function pose(){
  const b=S.body.x,br=Math.sin(S.t*Math.PI*2/4.6)*.65;
  const pelvis=[CX+b[1]*.2,410,0];
  const lumbar=add(pelvis,mv(rz(b[0]*.25),[0,-38,0]));
  const thorax=add(lumbar,mv(rz(b[0]*.65),[0,-66,0]));
  const chest=add(thorax,mv(rz(b[0]),[0,-62,0]));chest[1]+=br;
  const neck=add(chest,mv(rz(b[0]),[0,-27,0]));
  const bodyRot=rz(b[0]);
  const arms=[0,1].map(i=>{
   const side=i?1:-1,q=S.arms[i].x,up=clamp((q[0]-.15)/1.2)*3+clamp((q[3]-1.2)/1.5)*1.5;
   const shoulder=add(chest,mv(bodyRot,[side*58,-up,clamp(q[1]) *4]));
   const a=armPose(shoulder,q,S.fingers[i].x,S.spreads[i].x[0],side,bodyRot);
   a.handName=S.hand[i];a.clavicle3=[add(chest,[side*15,-3,0]),shoulder];return a;
  });
  const legs=[-1,1].map(side=>legPose(add(pelvis,[side*28,0,0]),[CX+side*35,634,0]));
  function T(x,y){const k=clamp((410-y)/166);return [CX+x+b[1]*.2-Math.sin(b[0])*Math.max(0,410-y),y+br*k];}
  const torso=[[-17,207],[-49,222],[-63,244],[-55,283],[-44,320],[-38,363],[-43,403],[-28,423],[0,428],[28,423],[43,403],[38,363],[44,320],[55,283],[63,244],[49,222],[17,207]].map(p=>T(...p));
  const ex=S.expr.x;
  const slot=Math.floor(S.t/4.8),start=slot*4.8+2.15+Math.sin(slot*12.1)**2*.8;
  const u=(S.t-start)/.24;const blink=u>=0&&u<1?(u<.35?smooth(u/.35):1-smooth((u-.35)/.65)):0;
  const head={x:neck[0]+b[2]*12,y:neck[1]-69+b[3]*3,tilt:b[0]*.4,yaw:b[2],pitch:b[3]};
  return {t:S.t,arms,legs,torso,neckBase:project(neck),head,
   joints:{pelvis,lumbar,thorax,chest,neck,head:[head.x,head.y,0]},
   eyes:{lidL:ex[0]*(1-blink),lidR:ex[1]*(1-blink),gx:ex[6],gy:ex[7]},
   brows:{ly:ex[2],ry:ex[3],lt:ex[4],rt:ex[5]},
   mouth:{open:clamp(S.mouth.x[0]),wide:clamp(S.mouth.x[1]),round:clamp(S.mouth.x[2]),smile:ex[8]},
   gesture:S.gesture,gain:S.gestureGain,breath:br,energy:S.energy.x[0]};
 }
 return {step,beat,pose,state:S};
}
// This fallback is explicitly illustrative. Actual speech requires timed phonemes.
function speechToVisemes(text,t0,dur){
 if(!Number.isFinite(t0)||!Number.isFinite(dur)||dur<=0)throw Error('Invalid speech interval');
 const chars=[...String(text).toLowerCase()].filter(c=>/[a-z\u0621-\u064a]/.test(c));
 const max=Math.max(1,Math.floor(dur/.13)),n=Math.min(chars.length,max),vis=[],beats=[];
 for(let i=0;i<n;i++){
  const c=chars[Math.floor(i*chars.length/n)];let v='C';
  if('mbpمب'.includes(c))v='M';else if('aeاأإآ'.includes(c))v='A';else if('ouو'.includes(c))v='O';else if('iyي'.includes(c))v='I';else if('fvف'.includes(c))v='F';
  vis.push({t:t0+i*dur/n,v});
 }
 vis.push({t:t0+dur,v:'X'});return {visemes:vis,beats};
}
function compile(script={}){
 const duration=script.duration==null?30:Number(script.duration);
 if(!Number.isFinite(duration)||duration<=0)throw Error('Invalid duration');
 const cues=(script.cues||[]).map(q=>{if(!Number.isFinite(q.t)||!Number.isFinite(q.dur)||q.t<0||q.t>=duration||q.dur<=0)throw Error('Invalid cue');if(!GESTURES[q.gesture])throw Error('Unknown gesture '+q.gesture);if(q.expr&&!EXPRESSIONS[q.expr])throw Error('Unknown expression');if(q.intensity!=null&&!Number.isFinite(q.intensity))throw Error('Invalid intensity');return {...q};}).sort((a,b)=>a.t-b.t);
 let vis=[];
 if(Array.isArray(script.visemes))vis=script.visemes.map(q=>{if(!Number.isFinite(q.t)||q.t<0||q.t>duration||!VISEMES[q.v])throw Error('Invalid viseme');return {...q};});
 else for(const s of script.speech||[]){if(!Number.isFinite(s.t)||s.t<0||s.t+s.dur>duration)throw Error('Speech outside timeline');vis.push(...speechToVisemes(s.text,s.t,s.dur).visemes);}
 vis.sort((a,b)=>a.t-b.t);
 // Close a manually supplied terminal shape unless explicitly ended already.
 if(vis.length&&vis[vis.length-1].v!=='X')vis.push({t:Math.min(duration,vis[vis.length-1].t+.18),v:'X'});
 const beats=(script.beats||[]).map(q=>{if(!Number.isFinite(q.t)||q.t<0||q.t>duration||!Number.isFinite(q.s??.5))throw Error('Invalid beat');return {...q,s:clamp(q.s??.5)};}).sort((a,b)=>a.t-b.t);
 return {duration,cues,vis,beats};
}
function inputAt(c,t){
 let cue=null;for(const q of c.cues){if(q.t>t)break;if(t<q.t+q.dur)cue=q;}
 let v='X';for(const q of c.vis){if(q.t>t)break;v=q.v;}
 return {gesture:cue?cue.gesture:'idle',expr:cue?cue.expr||'neutral':'neutral',cueT:cue?t-cue.t:-1,cueDur:cue?cue.dur:0,intensity:cue?.intensity??1,mouth:VISEMES[v]};
}
function sample(script,fps=FPS,duration){
 if(!Number.isFinite(fps)||fps<=0)throw Error('Invalid fps');
 const c=compile(script),p=createPerformer(),out=[];let t=0,bi=0;
 const dur=duration??c.duration;if(!Number.isFinite(dur)||dur<=0)throw Error('Invalid sample duration');
 const n=Math.ceil(dur*fps);
 for(let f=0;f<n;f++){
  const target=f/fps;
  while(t<target-1e-10){while(bi<c.beats.length&&c.beats[bi].t<=t+1e-10)p.beat(c.beats[bi++].s);
   const dt=Math.min(1/120,target-t);p.step(dt,inputAt(c,t));t+=dt;}
  out.push(p.pose());
 }return out;
}
const api={W,H,FPS,CX,FLOOR,LEN,LIMITS,HANDS,GESTURES,EXPRESSIONS,VISEMES,FINGER_LENGTHS,
 createPerformer,compile,inputAt,sample,speechToVisemes,envelope,math:{norm,sub,project}};
if(typeof module!=='undefined'&&module.exports)module.exports=api;root.ShadowRig=api;
})(typeof window!=='undefined'?window:globalThis);
