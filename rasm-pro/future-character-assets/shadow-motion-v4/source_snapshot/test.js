const assert=require('assert'),R=require('./rig.js'),fs=require('fs');
const script=JSON.parse(fs.readFileSync(__dirname+'/example_script.json','utf8'));
const a=R.sample(script,30),b=R.sample(script,30);
assert.deepStrictEqual(a,b); // deterministic
let maxL=0,clamped=0,maxStep=0,feet=0,n=0;
const d=(u,v)=>Math.hypot(u[0]-v[0],u[1]-v[1]);
a.forEach((p,i)=>{
 const flat=JSON.stringify(p); assert(!/null|NaN|Infinity/.test(flat),'non-finite at '+i);
 p.arms.forEach((m,k)=>{maxL=Math.max(maxL,Math.abs(d(m.s,m.e)-92),Math.abs(d(m.e,m.w)-82));if(m.clamped)clamped++;
   assert(m.w[0]>0&&m.w[0]<1280&&m.w[1]>0&&m.w[1]<720);
   if(i)maxStep=Math.max(maxStep,d(m.w,a[i-1].arms[k].w));
   m.hand.fingers.forEach(f=>f.pts.forEach(q=>assert(Number.isFinite(q[0]+q[1]))));});
 p.legs.forEach((l,k)=>{maxL=Math.max(maxL,Math.abs(d(l.s,l.e)-120),Math.abs(d(l.e,l.w)-118));feet=Math.max(feet,Math.abs(l.w[1]-634));});
 n++;});
assert(maxL<1e-6);assert(feet<1e-9);
const rep={frames:n,max_bone_length_error:maxL,clamped_arm_frames:clamped,max_wrist_px_per_frame_30fps:+maxStep.toFixed(2),max_foot_drift:feet,deterministic:true};
fs.writeFileSync(__dirname+'/test_report.json',JSON.stringify(rep,null,2));console.log(rep);
