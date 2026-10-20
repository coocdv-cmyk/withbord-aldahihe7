const fs=require('fs'),path=require('path'),assert=require('assert');
const R=require('./rig.js');
let maxError=0,clamped=0,checked=0;
for(const g of Object.keys(R.GESTURES))for(const e of Object.keys(R.EXPRESSIONS))for(let i=0;i<=30;i++){
 const p=R.pose(i/30,g,e,i/30);
 for(const a of[p.left,p.right]){
  const d=(u,v)=>Math.hypot(u[0]-v[0],u[1]-v[1]);
  maxError=Math.max(maxError,Math.abs(d(a.s,a.e)-a.l1),Math.abs(d(a.e,a.w)-a.l2));
  assert([a.s,a.e,a.w].flat().every(Number.isFinite));
  assert(a.w[0]>0&&a.w[0]<1280&&a.w[1]>0&&a.w[1]<720);
  if(a.clamped)clamped++;
 }
 checked++;
}
assert(maxError<1e-7);
assert.deepStrictEqual(R.pose(1.37,'compare','curious',.8),R.pose(1.37,'compare','curious',.8));
let maxStep=0;
for(const g of Object.keys(R.GESTURES)){
 let prev=null;
 for(let i=0;i<=10000;i++){
  const p=R.pose(0,g,'neutral',i/10000),a=[...p.left.e,...p.left.w,...p.right.e,...p.right.w];
  if(prev)maxStep=Math.max(maxStep,...a.map((v,j)=>Math.abs(v-prev[j])));
  prev=a;
 }
}
assert(maxStep<.1);
const rows=Array.from({length:R.duration*R.FPS},(_,i)=>R.scene(i/R.FPS));
fs.writeFileSync(path.join(__dirname,'reports','poses.json'),JSON.stringify(rows));
fs.writeFileSync(path.join(__dirname,'reports','rig_tests.json'),JSON.stringify({sampled_poses:checked,max_limb_length_error:maxError,clamped_endpoints:clamped,max_joint_coordinate_step_for_intensity_delta_0001:maxStep,deterministic:true,procedural:true,source_raster_assets:0,video_frames:rows.length,anatomical_realism_certified:false},null,2));
console.log(JSON.stringify({checked,maxError,clamped,frames:rows.length}));
