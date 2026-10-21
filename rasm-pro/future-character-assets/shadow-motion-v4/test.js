'use strict';
(async()=>{
const assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),vm=require('vm');
const R=require('./rig'),A=require('./audio');
const root=__dirname,results=[];let framesChecked=0,boneError=0,footDrift=0,maxWristStep=0,maxAccel=0;
const dist=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
async function test(name,fn){try{await fn();results.push({name,passed:true});}catch(e){results.push({name,passed:false,error:e.stack});}}
function near(a,b,tol=1e-7){assert(Math.abs(a-b)<tol,`${a} vs ${b}`);}
function finite(value){if(typeof value==='number')assert(Number.isFinite(value));else if(value&&typeof value==='object')Object.values(value).forEach(finite);}
function bone(a,b,len){boneError=Math.max(boneError,Math.abs(dist(a,b)-len));near(dist(a,b),len);}
function inspect(p){
 framesChecked++;finite(p);
 p.arms.forEach(a=>{
  bone(a.s3,a.e3,R.LEN.upper);bone(a.e3,a.w3,R.LEN.fore);
  a.angles.forEach((q,j)=>assert(q>=R.LIMITS[j][0]-1e-8&&q<=R.LIMITS[j][1]+1e-8));
  a.hand.fingers.forEach(f=>{assert.equal(f.pts3.length,4);for(let j=0;j<3;j++)bone(f.pts3[j],f.pts3[j+1],f.lengths[j]);});
  a.hand.palm.forEach(q=>assert(q[0]>0&&q[0]<1280&&q[1]>0&&q[1]<720));
 });
 p.legs.forEach((l,i)=>{assert(!l.clamped);bone(l.s3,l.e3,R.LEN.thigh);bone(l.e3,l.w3,R.LEN.shin);
  footDrift=Math.max(footDrift,dist(l.w3,[640+(i?35:-35),634,0]));});
}
await test('Every gesture: 3D fixed-length bones, finger joints, grounded ankles, authoring limits',()=>{
 for(const gesture of Object.keys(R.GESTURES))for(const intensity of [0,.5,1,1.15]){
  const poses=R.sample({duration:4,cues:[{t:.1,dur:3.6,gesture,intensity,expr:'neutral'}]});
  poses.forEach((p,i)=>{inspect(p);if(i)for(let a=0;a<2;a++)maxWristStep=Math.max(maxWristStep,dist(p.arms[a].w,poses[i-1].arms[a].w));
   if(i>1)for(let a=0;a<2;a++){const prev=poses[i-1].arms[a].w,prev2=poses[i-2].arms[a].w;maxAccel=Math.max(maxAccel,Math.hypot(...p.arms[a].w.map((v,k)=>(v-2*prev[k]+prev2[k])*900)));}
  });
 }
 assert(footDrift<1e-7);assert(maxWristStep<30,'Unbounded wrist jump');
});
await test('All 11 expressions settle as specified; neutral is not smiling',()=>{
 for(const expr of Object.keys(R.EXPRESSIONS)){const p=R.createPerformer();p.step(2,{expr});inspect(p.pose());near(p.pose().mouth.smile,R.EXPRESSIONS[expr][8],1e-5);}
 near(R.createPerformer().pose().mouth.smile,0);
});
await test('Frame counts, deterministic replay, 30/60 fps alignment',()=>{
 const s=JSON.parse(fs.readFileSync(path.join(root,'example_script.json'),'utf8'));
 const a=R.sample(s),b=R.sample(s),c=R.sample(s,60);assert.deepEqual(a,b);assert.equal(a.length,900);assert.equal(c.length,1800);
 for(let i=0;i<a.length;i+=10)for(let j=0;j<2;j++)near(dist(a[i].arms[j].w,c[i*2].arms[j].w),0,1e-7);
});
await test('Subsecond cues have positive smooth envelopes and zero outside bounds',()=>{
 for(const d of [.1,.3,.6,1,4]){near(R.envelope(0,d),0);near(R.envelope(d,d),0);assert(R.envelope(d*.5,d)>.99);assert(R.envelope(-.01,d)===0);}
});
await test('Explicit visemes override text; terminal shape closes; invalid timelines rejected',()=>{
 const c=R.compile({duration:3,speech:[{t:0,dur:2,text:'aaaaaa'}],visemes:[{t:.2,v:'M'},{t:.6,v:'O'}]});
 assert(!c.vis.some(v=>v.v==='A'));assert.equal(c.vis.at(-1).v,'X');assert.equal(R.inputAt(c,1).mouth[0],0);
 assert.equal(R.compile({duration:3,visemes:[],speech:[{t:0,dur:2,text:'a'}]}).vis.length,0);
 for(const x of [{duration:NaN},{duration:-1},{duration:2,visemes:[{t:3,v:'A'}]},{duration:2,cues:[{t:0,dur:1,gesture:'wrong'}]},{duration:2,beats:[{t:0,s:NaN}]}])assert.throws(()=>R.compile(x));
 assert.throws(()=>R.sample({duration:1},0));assert.throws(()=>R.sample({duration:1},30,-1));
});
await test('Audio silence stays still; stereo energy is measured without cancellation',()=>{
 const sr=16000,n=sr*3,z=new Float32Array(n);const silent=A.extract([z],sr);assert(silent.energy.every(v=>v===0));assert.equal(silent.beats.length,0);
 const x=Float32Array.from(z,(_,i)=>i>sr&&i<sr*2?.16*Math.sin(i*.1):0),y=Float32Array.from(x,v=>-v);
 const mono=A.extract([x],sr),stereo=A.extract([x,y],sr);assert(Math.max(...mono.energy)>.7);mono.energy.forEach((v,i)=>near(v,stereo.energy[i],1e-12));assert(stereo.beats.length<5);assert.equal(A.at(stereo,3).energy,0);
});
await test('Media master clock: low frame rate, pause, backwards seek, long jump',()=>{
 const c=R.compile({duration:30,cues:[{t:0,dur:30,gesture:'explain_r'}]}),clock=A.timeline(R,t=>R.inputAt(c,t));
 let p;for(let f=0;f<=100;f++)p=clock.advanceTo(f/10);near(p.t,10);assert.deepEqual(clock.advanceTo(10),p);
 near(clock.advanceTo(2).t,2);near(clock.advanceTo(1800).t,1800);near(clock.advanceTo(1800.1).t,1800.1);
});
await test('Canvas renderer executes full, closeup, transparent and debug modes',()=>{
 const C=require(process.env.CANVAS_MODULE||'C:/Users/USER/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@napi-rs/canvas');
 require('./draw');const c=C.createCanvas(1280,720),ctx=c.getContext('2d'),p=R.sample({duration:2,cues:[{t:0,dur:3,gesture:'compare'}]})[50];
 for(const o of [{},{studio:true,closeup:true},{skeleton:true},{bg:false,eyesOnly:true}])ShadowDraw.draw(ctx,p,o);
 const alpha=ctx.getImageData(0,0,1,1).data[3];assert.equal(alpha,0);assert(ctx.getImageData(640,300,1,1).data[3]>0);
});
await test('Browser event mocks: manual selection with audio, context and URL cleanup',async()=>{
 const ids=['view','play','restart','mode','gesture','expression','intensity','trigger','studio','closeup','skeleton','transparent','eyesOnly','assist','png','audioFile','scriptFile','clearAudio','audio','status'];
 const elements=Object.fromEntries(ids.map(id=>[id,{value:'',checked:false,textContent:'',files:[],add(){},getContext(){return {};},currentTime:0,paused:true,pause(){this.paused=true;this.onpause?.();},removeAttribute(){},load(){}}]));
 elements.mode.value='manual';elements.intensity.value='.9';elements.expression.value='neutral';
 let render,cb,unload,revoked=0,closed=0;const win={EXAMPLE_SCRIPT:{duration:30},addEventListener:(n,fn)=>{unload=fn;},AudioContext:class{async decodeAudioData(){return {numberOfChannels:1,sampleRate:16000,getChannelData:()=>new Float32Array(16000)};}async close(){closed++;}}};
 const code=fs.readFileSync(path.join(root,'app.js'),'utf8');
 const sandbox={window:win,ShadowRig:R,AudioMotion:A,ShadowDraw:{draw:(c,p)=>render=p},document:{getElementById:id=>elements[id]},Option:function(t,v){this.value=v;},requestAnimationFrame:fn=>cb=fn,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){revoked++;}},setTimeout};
 vm.runInNewContext(code,sandbox);elements.gesture.value='point_l';elements.gesture.onchange();cb(0);cb(500);assert.equal(render.gesture,'point_l');elements.expression.value='serious';elements.expression.onchange();cb(1000);assert.equal(elements.mode.value,'manual');assert.equal(render.gesture,'point_l');
 elements.audioFile.files=[{arrayBuffer:async()=>new ArrayBuffer(0)}];await elements.audioFile.onchange();assert.equal(closed,1);assert.equal(elements.mode.value,'manual');elements.gesture.value='point_r';elements.gesture.onchange();elements.audio.currentTime=1;cb(1100);assert.equal(render.gesture,'point_r');near(render.t,1);
 elements.clearAudio.onclick();assert.equal(elements.mode.value,'demo');assert.equal(revoked,1);unload();
 assert(!code.includes('Math.random'));assert(code.includes('finally{if(ac)await ac.close()'));assert(code.includes('URL.revokeObjectURL(url)'));
});
const script=JSON.parse(fs.readFileSync(path.join(root,'example_script.json'),'utf8'));
const old=require('./source_snapshot/rig');const oldPoses=old.sample(script,30);let oldMax=0;
oldPoses.forEach((p,i)=>{if(i)for(let a=0;a<2;a++)oldMax=Math.max(oldMax,dist(p.arms[a].w,oldPoses[i-1].arms[a].w));});
const report={passed:results.every(r=>r.passed),tests:results,frames_checked:framesChecked,max_3d_bone_length_error:boneError,max_ankle_drift:footDrift,max_wrist_px_per_frame_30fps:maxWristStep,max_projected_wrist_acceleration_px_s2:maxAccel,source_snapshot_same_demo_max_wrist_step_px:oldMax,notes:['Geometry checks do not establish human realism.','Pixel speed comparison depends on gesture size and is not a quality score.','Browser event logic was tested with mocks; the real browser/audio-device path needs user playback.']};
fs.writeFileSync(path.join(root,'reports/test_report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));process.exitCode=report.passed?0:1;
})().catch(e=>{console.error(e);process.exitCode=1;});
