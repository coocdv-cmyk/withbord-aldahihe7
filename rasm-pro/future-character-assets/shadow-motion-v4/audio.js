/* Acoustic activity, not phoneme recognition, sentiment analysis or semantics. */
(function(root){'use strict';
const clamp=x=>Math.max(0,Math.min(1,x));
function extract(channels,sampleRate){
 if(!channels?.length||!Number.isFinite(sampleRate)||sampleRate<=0)throw Error('Invalid PCM audio');
 const n=channels[0].length,hop=Math.max(1,Math.round(sampleRate*.02)),raw=[];
 if(channels.some(c=>c.length!==n))throw Error('Unequal channel lengths');
 for(let s=0;s<n;s+=hop){let sum=0,count=0;
  for(const ch of channels)for(let i=s;i<Math.min(n,s+hop);i++){sum+=ch[i]*ch[i];count++;}
  raw.push(Math.sqrt(sum/Math.max(1,count)));
 }
 const sorted=raw.slice().sort((a,b)=>a-b),q=p=>sorted[Math.min(sorted.length-1,Math.floor(sorted.length*p))]||0;
 const floor=Math.max(.003,q(.1)*1.7),ceiling=Math.max(.025,q(.9));
 const energy=[],beats=[];let value=0,lastBeat=-99,prev=0,gate=false;
 for(let i=0;i<raw.length;i++){
  const r=raw[i];gate=gate?r>floor*.8:r>floor*1.3;
  const target=gate?clamp((r-floor)/Math.max(.018,ceiling-floor)):0;
  const tau=target>value?.075:.16;
  value+=(target-value)*(1-Math.exp(-hop/sampleRate/tau));
  energy.push(value);
  const t=i*hop/sampleRate;
  if(value>.22&&value-prev>.035&&t-lastBeat>.44){beats.push({t,s:Math.min(.7,value)});lastBeat=t;}
  prev=value;
 }
 return {duration:n/sampleRate,hop:hop/sampleRate,energy,beats,method:'RMS activity only; no phoneme alignment'};
}
function at(track,t){
 if(!track||t<0||t>=track.duration)return {energy:0,mouth:[0,.5,0]};
 const x=t/track.hop,i=Math.floor(x),f=x-i;
 const e=(track.energy[i]||0)*(1-f)+(track.energy[i+1]||0)*f;
 return {energy:e,mouth:[Math.min(.52,e*.65),.5,0]};
}
// All state advances to the media clock. Large seeks reconstruct the last 2 s.
function timeline(rig,getInput,getBeats=()=>[]){
 let p=rig.createPerformer(),time=0,bi=0;
 function reset(t=0){p=rig.createPerformer();time=Math.max(0,t);p.state.t=time;
  const b=getBeats();bi=0;while(bi<b.length&&b[bi].t<time)bi++;}
 function advanceTo(target){
  if(!Number.isFinite(target)||target<0)throw Error('Invalid media time');
  if(target<time-1e-8||target-time>2.001)reset(Math.max(0,target-2));
  const beats=getBeats();
  while(time<target-1e-10){
   while(bi<beats.length&&beats[bi].t<=time+1e-9)p.beat(beats[bi++].s);
   const dt=Math.min(1/120,target-time);p.step(dt,getInput(time));time+=dt;
  }
  return p.pose();
 }
 return {advanceTo,reset,get time(){return time;}};
}
const api={extract,at,timeline};root.AudioMotion=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
