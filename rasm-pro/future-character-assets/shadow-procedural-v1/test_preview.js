/* Executes the browser application against a recording Canvas mock.
   This catches JS/runtime errors, not real browser visual compatibility. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let calls=0,callback;
const gradient={addColorStop(){}};
const context=new Proxy({}, {get(o,k){
 if(k==='createLinearGradient'||k==='createRadialGradient')return ()=>gradient;
 return (...args)=>{calls++;for(const a of args)if(typeof a==='number')assert(Number.isFinite(a));
  if(k==='ellipse')assert(args[2]>=0&&args[3]>=0);
 };
},set(o,k,v){o[k]=v;return true;}});
const controls={};
for(const id of ['play','auto','gesture','expression','amount','transparent','bones','png','status'])controls[id]={value:id==='amount'?'1':'',checked:id==='auto',textContent:'',add(o){if(!this.value)this.value=o.value;}};
const canvas={width:1280,height:720,getContext(){return context},toDataURL(){return 'data:image/png;base64,'}};
const sandbox={console,performance:{now:()=>0},Option:function(label,value){this.label=label;this.value=value},
 document:{querySelector:()=>canvas,getElementById:id=>controls[id],createElement:()=>({click(){}})},
 requestAnimationFrame:fn=>callback=fn};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname+'/rig.js','utf8'),sandbox);
const html=fs.readFileSync(__dirname+'/index.html','utf8');
vm.runInContext(html.split('<script>')[1].split('</script>')[0],sandbox);
controls.auto.checked=false;let cases=0;
for(const g of Object.keys(sandbox.ShadowRig.GESTURES))for(const e of Object.keys(sandbox.ShadowRig.EXPRESSIONS)){
 controls.gesture.value=g;controls.expression.value=e;
 for(const a of ['0','.5','1']){controls.amount.value=a;callback(cases*17);cases++;}
}
controls.transparent.checked=true;controls.bones.checked=true;callback(6000);
controls.play.onclick();callback(6016);controls.png.onclick();
const report={control_render_cases:cases,canvas_commands:calls,finite_coordinates:true,transparent_and_bones_controls_exercised:true,
 javascript_runtime_ok:true,actual_browser_visual_test:false,reason:'In-app browser could not reach localhost; use local index.html for interactive preview.'};
fs.writeFileSync(__dirname+'/reports/preview_runtime_test.json',JSON.stringify(report,null,2));
console.log(JSON.stringify(report));
