'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),{spawn,spawnSync}=require('child_process'),{once}=require('events'),crypto=require('crypto');
const root=path.resolve(__dirname,'..'),R=require('../rig'),A=require('../audio');require('../draw');
const C=require(process.env.CANVAS_MODULE||'C:/Users/USER/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@napi-rs/canvas');
const ffmpeg=process.env.FFMPEG||'D:/withbord inmation/studio/runtime/ffmpeg.exe';
const script=JSON.parse(fs.readFileSync(path.join(root,'example_script.json'),'utf8'));
const output=path.join(root,'preview'),audioOnly=process.argv.includes('--only-audio');
const stats=audioOnly?JSON.parse(fs.readFileSync(path.join(root,'reports/render_report.json'),'utf8')).videos.filter(v=>v.name!=='audio_response.mp4'):[];
const sourceHashes=Object.fromEntries(['rig.js','draw.js','audio.js','app.js','example_script.json','example_script.js'].map(n=>[n,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,n))).digest('hex')]));
const title=(ctx,txt,x,y,size=22)=>{ctx.font=`${size}px sans-serif`;ctx.fillStyle='#182330';ctx.fillText(txt,x,y);};
function oldDraw(){const box={};vm.runInNewContext(fs.readFileSync(path.join(root,'source_snapshot/draw.js'),'utf8'),box);return box.ShadowDraw;}
async function video(name,duration,paint,audio){
 const canvas=C.createCanvas(1280,720),ctx=canvas.getContext('2d');
 const args=['-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgba','-video_size','1280x720','-framerate','30','-i','pipe:0'];
 if(audio)args.push('-i',audio,'-map','0:v:0','-map','1:a:0','-af','apad','-c:a','aac','-b:a','128k');
 args.push('-t',String(duration),'-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',path.join(output,name));
 const proc=spawn(ffmpeg,args,{windowsHide:true,stdio:['pipe','ignore','pipe']});let errors='';proc.stderr.on('data',s=>errors+=s);proc.stdin.on('error',()=>{});
 const done=new Promise((resolve,reject)=>{proc.on('error',reject);proc.on('close',code=>code===0?resolve():reject(Error(errors||'ffmpeg exit '+code)));});
 const start=performance.now(),n=Math.ceil(duration*30);
 for(let f=0;f<n;f++){
  paint(ctx,f/30,f);
  const bytes=Buffer.from(ctx.getImageData(0,0,1280,720).data.buffer);
  if(!proc.stdin.write(bytes))await Promise.race([once(proc.stdin,'drain'),done.then(()=>{throw Error('Encoder stopped early');})]);
  if(f===60)fs.writeFileSync(path.join(output,name.replace('.mp4','.png')),canvas.toBuffer('image/png'));
 }
 proc.stdin.end();await done;
 const item={name,duration,submitted_frames:n,render_seconds:+((performance.now()-start)/1000).toFixed(3),bytes:fs.statSync(path.join(output,name)).size};stats.push(item);console.log(JSON.stringify(item));
}
async function main(){
 const frames=R.sample(script),srcRig=require('../source_snapshot/rig'),srcFrames=srcRig.sample(script,30),srcDraw=oldDraw();
 const oldCanvas=C.createCanvas(1280,720),newCanvas=C.createCanvas(1280,720),oc=oldCanvas.getContext('2d'),nc=newCanvas.getContext('2d');
 if(!audioOnly)await video('before_after.mp4',script.duration,(ctx,t,f)=>{
  srcDraw.draw(oc,srcFrames[f],{studio:false});ShadowDraw.draw(nc,frames[f],{studio:false});
  ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,1280,720);
  ctx.drawImage(oldCanvas,320,0,640,720,0,0,640,720);ctx.drawImage(newCanvas,320,0,640,720,640,0,640,720);
  ctx.fillStyle='#182330';ctx.fillRect(638,0,4,720);title(ctx,'BEFORE / supplied source',22,32);title(ctx,'AFTER / joint hierarchy',662,32);
  title(ctx,frames[f].gesture,675,690,19);
 });
 if(!audioOnly)await video('motion_after.mp4',script.duration,(ctx,t,f)=>{
  ShadowDraw.draw(ctx,frames[f],{studio:false,closeup:true});
  title(ctx,'SHADOW MOTION / joint-driven presenter',28,38,22);title(ctx,frames[f].gesture,28,682,22);
 });
 const fixture=path.join(output,'narration_fixture.wav');
 const source=process.argv.find((v,i)=>i>=2&&!v.startsWith('--'))||'D:/withbord inmation/rasm-pro/future-character-assets/validation-v2/audio/narration.wav';
 if(fs.existsSync(source)){
  fs.copyFileSync(source,fixture);
  const decode=spawnSync(ffmpeg,['-v','error','-i',fixture,'-f','f32le','-ac','1','-ar','22050','pipe:1'],{maxBuffer:128*1024*1024,windowsHide:true});
  if(decode.status!==0)throw Error(decode.stderr.toString());
  const raw=decode.stdout,pcm=new Float32Array(raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength)),features=A.extract([pcm],22050);
  const c=R.compile({...script,duration:Math.max(script.duration,features.duration)});
  const clock=A.timeline(R,t=>({...R.inputAt(c,t),...A.at(features,t)}),()=>features.beats);
  await video('audio_response.mp4',features.duration,(ctx,t)=>{
   const p=clock.advanceTo(t);ShadowDraw.draw(ctx,p,{studio:false,closeup:true});
   title(ctx,'LOCAL AUDIO FIXTURE / acoustic mouth activity',28,38,22);
   title(ctx,'Gestures: authored timeline. Mouth: energy only.',28,685,20);
   ctx.fillStyle='#627e72';ctx.fillRect(28,57,A.at(features,t).energy*180,5);
  },fixture);
  fs.writeFileSync(path.join(root,'reports/audio_features.json'),JSON.stringify({source_fixture:source,voice:process.argv.some(v=>v.toLowerCase().endsWith('.wav'))?'Caller-supplied fixture':'Existing Microsoft Zira Desktop female system TTS fixture; not a human performer or final brand voice',duration:features.duration,method:features.method,analysis_hop:features.hop,detected_emphasis_events:features.beats.length,max_energy:Math.max(...features.energy),note:'Existing local voice fixture copied only for synchronization testing. No voice model was trained or changed.'},null,2));
 }
 ShadowDraw.draw(nc,frames[60],{bg:false,studio:false});fs.writeFileSync(path.join(output,'character_transparent.png'),newCanvas.toBuffer('image/png'));
 ShadowDraw.draw(nc,frames[60],{skeleton:true,studio:false,closeup:true});fs.writeFileSync(path.join(output,'joint_debug.png'),newCanvas.toBuffer('image/png'));
 // Dense temporal contact sheet: actual frames from the same renderer, not a substitute drawing.
 const sheet=C.createCanvas(1600,900),sc=sheet.getContext('2d');
 [0,.3,.6,1,1.5,2,3,3.8,4.5,5,6,8.8,10,13.5,17.5,21.3,25,26,28,29].forEach((t,i)=>{
  const p=frames[Math.min(frames.length-1,Math.round(t*30))];ShadowDraw.draw(nc,p,{studio:false,closeup:true});
  sc.drawImage(newCanvas,(i%4)*400,Math.floor(i/4)*180,400,180);title(sc,`${t.toFixed(1)}s  ${p.gesture}`,(i%4)*400+8,Math.floor(i/4)*180+20,14);
 });
 fs.writeFileSync(path.join(output,'motion_contact_sheet.png'),sheet.toBuffer('image/png'));
 for(const [n,h] of Object.entries(sourceHashes))if(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,n))).digest('hex')!==h)throw Error('Source changed while rendering: '+n);
 fs.writeFileSync(path.join(root,'reports/render_report.json'),JSON.stringify({renderer:'@napi-rs/canvas executing draw.js directly',source_sha256:sourceHashes,resolution:'1280x720',fps:30,videos:stats,notes:['No generated raster character or frame library. All geometry is procedural.','MP4 background is baked; character_transparent.png is RGBA.','Render times are measurements of this machine and these short demonstrations only.','submitted_frames counts Canvas frames. FFmpeg may trim the final partial audio frame; media_validation.json contains encoded frame counts.']},null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
