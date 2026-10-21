(function(){'use strict';
const $=id=>document.getElementById(id),R=ShadowRig,A=AudioMotion;
const ui=Object.fromEntries(['view','play','restart','mode','gesture','expression','intensity','trigger','studio','closeup','skeleton','transparent','eyesOnly','assist','png','audioFile','scriptFile','clearAudio','audio','status'].map(id=>[id,$(id)]));
const ctx=ui.view.getContext('2d');
for(const g of Object.keys(R.GESTURES))ui.gesture.add(new Option(g,g));
for(const e of Object.keys(R.EXPRESSIONS))ui.expression.add(new Option(e,e));
let compiled=R.compile(window.EXAMPLE_SCRIPT),track=null,url=null,running=true,localTime=0,lastStamp=null,manualStart=0,loadToken=0;
ui.gesture.value='explain_r';
function input(t){
 const mode=ui.mode.value,hasAudio=!!url;
 let v=mode==='demo'||mode==='script'?R.inputAt(compiled,t):{
  gesture:ui.gesture.value,expr:ui.expression.value,intensity:Number(ui.intensity.value),cueT:t-manualStart,cueDur:4.2,mouth:R.VISEMES.X};
 if(hasAudio){
  const ac=A.at(track,t);v={...v,energy:ac.energy};
  if(!(mode==='script'&&compiled.vis.length))v.mouth=ac.mouth;
  if(ui.assist.checked&&mode==='manual'&&t-manualStart>4.2){
   const slot=Math.floor(t/5.8);v.gesture=ac.energy>.08?(slot%2?'explain_l':'explain_r'):'idle';
   v.cueT=t-slot*5.8;v.cueDur=5.4;v.intensity=.65;
  }
 }
 return v;
}
function beats(){return url?track?.beats||[]:compiled.beats;}
const clock=A.timeline(R,input,beats);
function status(s){ui.status.textContent=s;}
function time(){return url?ui.audio.currentTime:localTime;}
function redraw(t){ShadowDraw.draw(ctx,clock.advanceTo(t),{studio:ui.studio.checked,closeup:ui.closeup.checked,skeleton:ui.skeleton.checked,bg:!ui.transparent.checked,eyesOnly:ui.eyesOnly.checked});}
function invalidate(){clock.reset(Math.max(0,time()-1.5));redraw(time());}
function manual(){ui.mode.value='manual';manualStart=time();invalidate();}
ui.gesture.onchange=manual;ui.expression.onchange=manual;ui.trigger.onclick=manual;
ui.intensity.oninput=()=>{if(ui.mode.value!=='manual')manual();};
ui.mode.onchange=()=>{manualStart=time();invalidate();};
for(const id of ['studio','closeup','skeleton','transparent','eyesOnly','assist'])ui[id].onchange=()=>redraw(time());
function setPlaying(on){running=on;ui.play.textContent=on?'إيقاف':'تشغيل';lastStamp=null;}
ui.play.onclick=async()=>{
 if(url){if(ui.audio.paused){try{await ui.audio.play();}catch(e){status('اضغط تشغيل الصوت: '+e.message);}}else ui.audio.pause();}
 else setPlaying(!running);
};
ui.restart.onclick=()=>{if(url)ui.audio.currentTime=0;else localTime=0;manualStart=0;clock.reset();redraw(0);};
ui.audio.onplay=()=>setPlaying(true);ui.audio.onpause=()=>setPlaying(false);ui.audio.onended=()=>setPlaying(false);
ui.audio.onseeked=()=>{clock.reset(Math.max(0,time()-2));redraw(time());};
ui.audio.onerror=()=>status('تعذّر تشغيل ملف الصوت. جرّب WAV أو MP3 مدعومًا في المتصفح.');
function release(){ui.audio.pause();ui.audio.removeAttribute('src');ui.audio.load();if(url)URL.revokeObjectURL(url);url=null;track=null;}
ui.clearAudio.onclick=()=>{loadToken++;release();localTime=0;manualStart=0;clock.reset();ui.mode.value='demo';setPlaying(true);status('تمت إزالة الصوت. العرض بدون صوت.');};
ui.audioFile.onchange=async()=>{
 const file=ui.audioFile.files[0];if(!file)return;const token=++loadToken;status('تحليل شدة التسجيل محليًا…');
 let ac;
 try{
  const bytes=await file.arrayBuffer();ac=new (window.AudioContext||window.webkitAudioContext)();
  const buffer=await ac.decodeAudioData(bytes);
  const features=A.extract(Array.from({length:buffer.numberOfChannels},(_,i)=>buffer.getChannelData(i)),buffer.sampleRate);
  if(token!==loadToken)return;
  release();track=features;url=URL.createObjectURL(file);ui.audio.src=url;ui.mode.value='manual';localTime=0;manualStart=0;clock.reset();setPlaying(false);redraw(0);
  status('الصوت جاهز. اضغط تشغيل؛ الفم يستجيب لشدة الكلام. اختر الإيماءات حسب المعنى أو حمّل توقيتًا مطابقًا.');
 }catch(e){if(token===loadToken)status('تعذّر قراءة الصوت: '+e.message);}
 finally{if(ac)await ac.close().catch(()=>{});}
};
ui.scriptFile.onchange=async()=>{
 try{const file=ui.scriptFile.files[0];if(!file)return;const c=R.compile(JSON.parse(await file.text()));compiled=c;ui.mode.value='script';clock.reset(Math.max(0,time()-2));redraw(time());status('تم تحميل التوقيت. يجب أن تكون أحداث الفم والحركات مطابقة لتسجيلك.');}
 catch(e){status('ملف التوقيت غير صالح: '+e.message);}
};
ui.png.onclick=()=>{ui.view.toBlob(blob=>{if(!blob)return;const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download='shadow-pose.png';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);},'image/png');};
window.addEventListener('beforeunload',()=>{loadToken++;release();});
function frame(stamp){
 if(lastStamp===null)lastStamp=stamp;
 if(!url&&running){localTime+=Math.max(0,(stamp-lastStamp)/1000);
  if(ui.mode.value==='demo'&&localTime>=compiled.duration){localTime%=compiled.duration;clock.reset();}}
 lastStamp=stamp;redraw(time());requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
})();
