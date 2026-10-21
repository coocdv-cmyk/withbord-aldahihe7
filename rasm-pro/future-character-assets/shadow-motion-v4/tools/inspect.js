const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'..');
const canvas=require(process.env.CANVAS_MODULE||'C:/Users/USER/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@napi-rs/canvas');
const R=require('../rig');require('../draw');
const out=canvas.createCanvas(1600,Math.ceil(Object.keys(R.GESTURES).length/5)*320),c=out.getContext('2d');
Object.keys(R.GESTURES).forEach((g,i)=>{
 const p=R.createPerformer();for(let f=0;f<240;f++)p.step(1/120,{gesture:g,expr:'neutral',cueT:f/120,cueDur:5});
 const tile=canvas.createCanvas(640,720),ctx=tile.getContext('2d');
 // Full body in a narrower viewport, preserving the rig's aspect ratio.
 const full=canvas.createCanvas(1280,720);ShadowDraw.draw(full.getContext('2d'),p.pose(),{studio:false});
 ctx.drawImage(full,320,0,640,720,0,0,640,720);
 c.drawImage(tile,(i%5)*320,Math.floor(i/5)*320,320,300);
 c.fillStyle='#182330';c.font='16px sans-serif';c.fillText(g,(i%5)*320+12,Math.floor(i/5)*320+318);
});
fs.writeFileSync(path.join(root,'preview/poses.png'),out.toBuffer('image/png'));
console.log('poses.png');
