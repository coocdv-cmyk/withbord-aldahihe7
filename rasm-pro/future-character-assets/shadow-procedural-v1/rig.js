/* Original procedural silhouette. No source image, mesh texture, or frame atlas. */
(function(root){
  'use strict';
  const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
  const ease=x=>{x=clamp(x);return x*x*x*(x*(x*6-15)+10);};
  const lerp=(a,b,t)=>a+(b-a)*t;
  const mix=(a,b,t)=>a.map((v,i)=>lerp(v,b[i],t));
  const EXPRESSIONS={
    neutral:{l:13,r:13,sl:0,sr:0,gx:0,gy:0,tilt:0},
    curious:{l:19,r:12,sl:-.08,sr:0,gx:1,gy:-1,tilt:-.065},
    thinking:{l:10,r:10,sl:0,sr:0,gx:-4,gy:-3,tilt:.045},
    skeptical:{l:8,r:15,sl:.12,sr:0,gx:0,gy:0,tilt:.045},
    surprised:{l:23,r:23,sl:0,sr:0,gx:0,gy:-1,tilt:0},
    concerned:{l:10,r:10,sl:-.18,sr:.18,gx:0,gy:1,tilt:-.025},
    serious:{l:8,r:8,sl:.16,sr:-.16,gx:0,gy:0,tilt:0},
    pleased:{l:7,r:7,sl:0,sr:0,gx:0,gy:-1,tilt:-.035},
    unsure:{l:11,r:15,sl:-.1,sr:.08,gx:3,gy:0,tilt:.07},
    relieved:{l:9,r:9,sl:0,sr:0,gx:0,gy:1,tilt:.025}
  };
  const GESTURES={
    idle:{l:[574,438],r:[706,438],lh:'relax',rh:'relax'},
    explain:{l:[536,350],r:[706,438],lh:'open',rh:'relax'},
    explain_other:{l:[574,438],r:[744,350],lh:'relax',rh:'open'},
    compare:{l:[525,345],r:[755,345],lh:'open',rh:'open'},
    question:{l:[542,365],r:[738,365],lh:'open',rh:'open'},
    point_left:{l:[478,315],r:[706,438],lh:'point_left',rh:'relax'},
    point_right:{l:[574,438],r:[802,315],lh:'relax',rh:'point_right'},
    emphasize:{l:[564,317],r:[706,438],lh:'point_up',rh:'relax'},
    welcome:{l:[509,365],r:[771,365],lh:'open',rh:'open'},
    think:{l:[578,335],r:[710,402],lh:'relax',rh:'relax'}
  };
  const SCENES=[
    ['idle','neutral','Calm presence'],['explain','curious','Ask a useful question'],
    ['explain_other','serious','Explain one idea'],['compare','thinking','Compare two possibilities'],
    ['point_left','neutral','Direct attention left'],['point_right','skeptical','Check the evidence'],
    ['emphasize','serious','Emphasize one point'],['question','unsure','Acknowledge uncertainty'],
    ['welcome','pleased','Welcome a discovery'],['idle','relieved','Pause and conclude']
  ];
  function ik(s,target,a,b,side){
    let dx=target[0]-s[0],dy=target[1]-s[1];
    let raw=Math.hypot(dx,dy),d=clamp(raw,Math.abs(a-b)+.01,a+b-.01);
    let u=raw>1e-8?[dx/raw,dy/raw]:[0,1];
    let w=[s[0]+u[0]*d,s[1]+u[1]*d];
    let q=(a*a-b*b+d*d)/(2*d),h=Math.sqrt(Math.max(0,a*a-q*q));
    return {s:s,e:[s[0]+u[0]*q-u[1]*h*side,s[1]+u[1]*q+u[0]*h*side],
      w:w,target:target,clamped:Math.abs(raw-d)>.001,l1:a,l2:b};
  }
  function pose(t,gesture='idle',expression='neutral',amount=1){
    let target=GESTURES[gesture]||GESTURES.idle,neutral=GESTURES.idle;
    let gain=ease(amount),breathe=.8*Math.sin(t*Math.PI/2.3);
    let lean=gesture==='explain'?-2*gain:gesture==='explain_other'?2*gain:0;
    let chest=[640+lean,360+breathe];
    let ls=[594+lean,292+breathe],rs=[686+lean,292+breathe];
    let lw=mix(neutral.l,target.l,gain),rw=mix(neutral.r,target.r,gain);
    lw[1]+=breathe;rw[1]+=breathe;
    let ex=EXPRESSIONS[expression]||EXPRESSIONS.neutral,eye={};
    Object.keys(ex).forEach(k=>eye[k]=lerp(EXPRESSIONS.neutral[k],ex[k],gain));
    // Deterministic authored blink, no random timing or constant motion.
    const phase=(t+1.2)%5.1;
    let blink=phase<.22?Math.sin(Math.PI*phase/.22)**2:0;
    let lh=gain>.45?target.lh:'relax',rh=gain>.45?target.rh:'relax';
    return {t,gesture,expression,amount:gain,chest,head:[640+lean*.6,214+breathe],eye,blink,
      left:ik(ls,lw,82,77,-1),right:ik(rs,rw,82,77,1),lh,rh,
      hips:[[616,449],[664,449]],knees:[[608,536],[672,536]],ankles:[[604,618],[676,618]]};
  }
  function scene(t){
    let i=Math.min(SCENES.length-1,Math.floor(t/3)),local=t-i*3;
    let [g,e,label]=SCENES[i];
    let amount=local<.65?ease(local/.65):local>2.15?1-ease((local-2.15)/.85):1;
    return {...pose(t,g,e,amount),scene:i,label};
  }
  const api={W:1280,H:720,FPS:30,duration:30,EXPRESSIONS,GESTURES,SCENES,pose,scene,ik};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.ShadowRig=api;
})(typeof window!=='undefined'?window:globalThis);
