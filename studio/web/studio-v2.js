const $=id=>document.getElementById(id);
let token='',project=null,selected=0,activeJob=null,previewVersion=0,busy=false;
let assetMap=new Map(),saveTimer;
function toast(message){$('toast').textContent=message;$('toast').style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').style.display='none',6500)}
const safe=fn=>async(...args)=>{try{return await fn(...args)}catch(e){toast(e.message)}};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
async function api(path,data){
  if(data!==undefined&&!token)throw Error('الاستوديو لسه بيتجهز؛ انتظر لحظة');
  const res=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':token},body:JSON.stringify(data)});
  if(!res.ok){let error=await res.json();throw Error(error.error||'تعذر إكمال الطلب')}
  return res.headers.get('content-type').includes('application/json')?res.json():res.blob();
}
function setBusy(value){busy=value;for(const id of ['plan','render','preview-motion','generate','watch-demo','demo-yusuf','demo-business'])$(id).disabled=value||!token||(['render','preview-motion'].includes(id)&&!project)}
function sync(){
  if(!project)return;
  for(const k of ['title','resolution','accent','renderer','paper'])project[k]=$(k).value;
  project.hand=$('hand').checked;project.camera=$('camera').checked;
  project.duration=project.scenes.reduce((sum,s)=>sum+Number(s.duration),0);
  $('summary').textContent=`${project.scenes.length} مشاهد · ${project.duration.toFixed(2)} ثانية · ${project.renderer==='whiteboard'?'رسم باليد والقلم':'رموز'}`;
}
function queueSave(){if(!project||busy)return;clearTimeout(saveTimer);saveTimer=setTimeout(safe(async()=>{sync();await api('/api/save',project);try{localStorage.setItem('rasm-project',project.id)}catch{}}),1000)}
function readOptions(){return {title:$('title').value,script:$('script').value,duration:+$('duration').value,scene_length:+$('scene-length').value,
  domain:$('domain').value,planner:$('planner').value,renderer:$('renderer').value,paper:$('paper').value,accent:$('accent').value,
  hand:$('hand').checked,camera:$('camera').checked,resolution:$('resolution').value}}
async function loadProject(p){
  project=p;selected=0;
  for(const k of ['title','script','domain','planner','resolution','accent'])$(k).value=p[k];
  $('renderer').value=p.renderer||'legacy';$('paper').value=p.paper||'cream';$('hand').checked=p.hand!==false;$('camera').checked=p.camera!==false;
  $('duration').value=p.scenes.reduce((a,s)=>a+Number(s.duration),0).toFixed(2);
  drawScenes();setBusy(false);await preview();queueSave();
}
async function preview(){
  if(!project)return;sync();const revision=++previewVersion;
  const blob=await api('/api/preview',{project,index:selected});if(revision!==previewVersion)return;
  const img=$('preview');if(img.dataset.url)URL.revokeObjectURL(img.dataset.url);img.dataset.url=URL.createObjectURL(blob);img.src=img.dataset.url;
  img.hidden=false;$('empty').hidden=true;$('motion-preview').pause();$('motion-preview').hidden=true;
}
function drawScenes(){
  sync();$('scene-list').replaceChildren();
  project.scenes.forEach((scene,index)=>{
    const card=el('div',undefined,'scene'+(index===selected?' active':''));
    const head=el('div',undefined,'scene-head');head.append(el('b',String(index+1).padStart(2,'0')));
    const title=el('input');title.value=scene.title;title.setAttribute('aria-label','عنوان المشهد');title.onchange=safe(async()=>{scene.title=title.value;selected=index;queueSave();await preview()});
    const duration=el('input',undefined,'scene-duration');duration.type='number';duration.min=1;duration.max=3600;duration.step='.01';duration.value=Number(scene.duration).toFixed(2);duration.setAttribute('aria-label','مدة المشهد');duration.onchange=()=>{scene.duration=+duration.value;sync();queueSave()};
    head.append(title,duration,el('small','ث'));
    const text=el('textarea');text.value=scene.text;text.setAttribute('aria-label','النص المرجعي للمشهد');text.onchange=()=>{scene.text=text.value;queueSave()};
    const controls=el('div',undefined,'scene-actions');
    const layout=el('select');layout.setAttribute('aria-label','تكوين المشهد');
    for(const [value,name] of [['focus','تكوين قصصي'],['compare','مقارنة متوازنة']]){const option=el('option',name);option.value=value;layout.append(option)}
    layout.value=scene.layout==='compare'?'compare':'focus';layout.onchange=safe(async()=>{scene.layout=layout.value;selected=index;drawScenes();await preview()});controls.append(layout);
    scene.assets.forEach((aid,ai)=>{const chip=el('button',(assetMap.get(aid)?.name||aid)+' ×','asset-chip');chip.title='إزالة الرسمة';chip.onclick=safe(async()=>{scene.assets.splice(ai,1);scene.placements={};scene.labels={};selected=index;drawScenes();await preview()});controls.append(chip)});
    for(const [caption,delta] of [['↑',-1],['↓',1]]){const button=el('button',caption,'quiet');button.setAttribute('aria-label',delta<0?'تقديم المشهد':'تأخير المشهد');button.onclick=safe(async()=>{const target=index+delta;if(target<0||target>=project.scenes.length)return;[project.scenes[index],project.scenes[target]]=[project.scenes[target],project.scenes[index]];selected=target;drawScenes();await preview()});controls.append(button)}
    const duplicate=el('button','نسخ','quiet');duplicate.onclick=safe(async()=>{if(project.scenes.length>=120)throw Error('حد المشروع 120 مشهدًا');project.scenes.splice(index+1,0,JSON.parse(JSON.stringify(scene)));selected=index+1;drawScenes();await preview()});controls.append(duplicate);
    const remove=el('button','حذف','quiet');remove.onclick=safe(async()=>{if(project.scenes.length===1)return;project.scenes.splice(index,1);selected=Math.min(selected,project.scenes.length-1);drawScenes();await preview()});controls.append(remove);
    card.append(head,text,controls);
    if(scene.assets.length===0)card.append(el('small','المشهد يحتاج رسمة؛ اختر من المكتبة أو استورد أصلًا مناسبًا.'));
    card.onclick=safe(async event=>{if(['INPUT','TEXTAREA','BUTTON','SELECT'].includes(event.target.tagName))return;selected=index;drawScenes();await preview()});
    $('scene-list').append(card);
  });
  placements();queueSave();
}
function placements(){
  $('placements').replaceChildren();if(!project)return;const scene=project.scenes[selected],n=scene.assets.length;
  scene.assets.forEach((aid,i)=>{
    const box=el('div',undefined,'placement');box.append(el('strong',assetMap.get(aid)?.name||aid));
    const label=el('label','اسم يظهر بجانب الرسمة');const input=el('input');input.value=scene.labels?.[i]||'';input.maxLength=60;input.onchange=safe(async()=>{scene.labels=scene.labels||{};scene.labels[i]=input.value;queueSave();await preview()});label.append(input);box.append(label);
    const defaults=n===1?{x:.5,y:.59,size:.55}:i===0?{x:.66,y:.58,size:.55}:i===1?{x:.25,y:.62,size:.29}:{x:.35,y:.80,size:.24};
    const row=el('div',undefined,'three');
    for(const [key,name,min,max] of [['x','أفقي',.05,.95],['y','رأسي',.2,.88],['size','الحجم',.04,.6]]){
      const field=el('label',name),range=el('input');range.type='range';range.min=min;range.max=max;range.step='.01';range.value=scene.placements?.[i]?.[key]??defaults[key];
      range.onchange=safe(async()=>{scene.placements=scene.placements||{};scene.placements[i]=scene.placements[i]||{...defaults};scene.placements[i][key]=+range.value;queueSave();await preview()});field.append(range);row.append(field);
    }
    box.append(row);const reset=el('button','استعادة موضع القالب','quiet');reset.onclick=safe(async()=>{if(scene.placements)delete scene.placements[i];placements();queueSave();await preview()});box.append(reset);$('placements').append(box);
  });
}
async function assets(){
  const list=await api('/api/assets?q='+encodeURIComponent($('search').value)+'&kind='+$('asset-kind').value+'&domain='+$('library-domain').value);
  $('assets').replaceChildren();
  for(const a of list){assetMap.set(a.id,a);const card=el('button',undefined,'asset-card'+(a.kind==='illustration'?'':' icon'));const img=el('img');img.src='/library/'+encodeURIComponent(a.file);img.alt=a.name;img.loading='lazy';card.append(img,el('span',a.name),el('em',a.kind==='illustration'?'رسمة قابلة للكشف التدريجي':'رمز مساعد'));card.title=a.license;card.onclick=safe(()=>addAsset(a.id));$('assets').append(card)}
  if(!list.length)$('assets').append(el('p','لا توجد نتائج؛ جرّب كلمة أخرى أو استورد رسمة.'));
}
async function addAsset(aid){if(!project)throw Error('جهز المشاهد أولًا');const scene=project.scenes[selected];if(scene.assets.length>=6)throw Error('حد المشهد 6 رسومات؛ احذف رسمة أو أنشئ مشهدًا جديدًا');scene.assets.push(aid);drawScenes();await preview()}
async function pollJob(id){
  activeJob=id;$('job-box').hidden=false;$('cancel').hidden=false;$('downloads').replaceChildren();
  try{while(true){const job=await api('/api/job/'+id);$('job-message').textContent=job.message;$('progress').value=job.progress;if(job.status==='done')return job;if(job.status==='error')throw Error(job.message);await new Promise(resolve=>setTimeout(resolve,900))}}
  finally{activeJob=null;$('cancel').hidden=true;setBusy(false)}
}
$('plan').onclick=safe(async()=>{setBusy(true);try{const job=await api('/api/plan-start',readOptions());const result=await pollJob(job.id);await loadProject(result.project);toast('الخطة جاهزة؛ راجع الرسومات والتوقيت قبل التصدير')}finally{setBusy(false)}});
for(const name of ['yusuf','business'])$('demo-'+name).onclick=safe(async()=>{if(busy)throw Error('انتظر اكتمال المهمة الحالية');await loadProject(await api('/api/demo?name='+name));toast('العينة جاهزة؛ جرّب معاينة الحركة أو التصدير')});
$('save').onclick=safe(async()=>{if(!project)throw Error('جهّز المشاهد أولًا');sync();await api('/api/save',project);toast('تم الحفظ على جهازك')});
$('load').onclick=safe(async()=>{const list=await api('/api/projects');$('project-items').replaceChildren();for(const p of list){const button=el('button',p.title,'quiet');button.onclick=safe(async()=>{await loadProject(await api('/api/project/'+p.file));$('projects').close()});$('project-items').append(button)}if(!list.length)$('project-items').append(el('p','لا توجد مشاريع محفوظة'));$('projects').showModal()});
$('close-projects').onclick=()=>$('projects').close();
$('duration').onchange=safe(async()=>{if(!project)return;const target=+$('duration').value,n=project.scenes.length;if(!Number.isFinite(target)||target<n||target>7200)throw Error('خصص ثانية على الأقل لكل مشهد، وبحد أقصى ساعتين للفيديو');const sum=project.scenes.reduce((a,s)=>a+Number(s.duration),0);project.scenes.forEach(s=>s.duration=1+(target-n)*s.duration/sum);drawScenes();await preview()});
for(const id of ['accent','paper','renderer','hand','camera','resolution'])$(id).onchange=safe(async()=>{if(!project)return;sync();queueSave();await preview()});
function showVideo(url){$('preview').hidden=true;$('empty').hidden=true;const video=$('motion-preview');video.src=url;video.poster=url.slice(0,url.lastIndexOf('/')+1)+'scene_001.png';video.hidden=false;video.load()}
$('watch-demo').onclick=safe(async()=>{if(busy)throw Error('انتظر اكتمال المهمة الحالية');const result=await api('/api/demo-result');await loadProject(result.project);showVideo(result.url);$('job-box').hidden=false;$('cancel').hidden=true;$('progress').value=100;$('job-message').textContent='عينة جاهزة: 32 ثانية — اضغط تشغيل';$('downloads').replaceChildren();const a=el('a','تنزيل العينة');a.href=result.url;a.download='whiteboard-demo.mp4';$('downloads').append(a);$('preview-wrap').scrollIntoView({behavior:'smooth',block:'center'})});
async function exportVideo(previewOnly){
  if(!project)throw Error('جهز المشاهد أولًا');sync();
  if(!previewOnly&&$('script').value.trim()!==project.script.trim())throw Error('السكريبت اتغير؛ أعد تجهيز خطة الرسم قبل تصدير النص الجديد');
  setBusy(true);
  try{
    if(!previewOnly)await api('/api/save',project);
    const task=await api(previewOnly?'/api/preview-motion':'/api/render',previewOnly?{project,index:selected}:project);
    const result=await pollJob(task.id);showVideo(result.url);
    if(!previewOnly){const base=result.url.slice(0,result.url.lastIndexOf('/')+1);for(const [label,url,file] of [
      ['الفيديو الكامل',result.url,'video.mp4'],['ملف التوقيت',base+'captions.srt','captions.srt'],['المشروع',base+'project.json','project.json'],['مصادر الأصول',base+'asset-credits.json','asset-credits.json'],
      ...result.clips.map((url,i)=>['مشهد '+(i+1),url,'scene_'+(i+1)+'.mp4'])]){const a=el('a',label);a.href=url;a.download=file;$('downloads').append(a)}
      if(result.board){const a=el('a','اللوحة المتراكمة');a.href=result.board;a.target='_blank';a.rel='noopener';$('downloads').append(a)}
    }toast(previewOnly?'معاينة الحركة جاهزة؛ اضغط تشغيل':'الفيديو الصامت جاهز');
  }finally{setBusy(false)}
}
$('render').onclick=safe(()=>exportVideo(false));$('preview-motion').onclick=safe(()=>exportVideo(true));$('cancel').onclick=safe(async()=>{if(activeJob)await api('/api/cancel',{id:activeJob})});
$('search-local').onclick=safe(assets);for(const id of ['asset-kind','library-domain'])$(id).onchange=safe(assets);$('search').onkeydown=e=>{if(e.key==='Enter')safe(assets)()};
$('import').onchange=safe(async event=>{const file=event.target.files[0];if(!file)return;if(file.size>15000000)throw Error('حد الصورة 15 ميجابايت');const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(file)});const result=await api('/api/import',{name:file.name,data});$('asset-kind').value='illustration';$('search').value='';await assets();if(project)await addAsset(result.id);toast('تم الاستيراد؛ راجع حواف الصورة وتناسقها مع المشروع')});
$('online').onclick=safe(async()=>{const query=$('online-query').value.trim();if(!query)throw Error('اكتب كلمات البحث');$('online').disabled=true;try{const list=await api('/api/search-online',{query});$('online-results').replaceChildren();for(const item of list){const card=el('div',undefined,'remote');const img=el('img');img.src=item.thumb;img.alt=item.title;img.referrerPolicy='no-referrer';const link=el('a','المصدر والترخيص');link.href=item.page;link.target='_blank';link.rel='noopener noreferrer';const button=el('button','استيراد','quiet');button.onclick=safe(async()=>{button.disabled=true;try{const a=await api('/api/import-online',item);await assets();if(project)await addAsset(a.id);toast('تم حفظ الأصل وبيانات مصدره')}finally{button.disabled=false}});card.append(img,el('p',item.title),el('p',item.license),link,button);$('online-results').append(card)}if(!list.length)toast('لا توجد نتائج')}finally{$('online').disabled=false}});
$('generate').onclick=safe(async()=>{setBusy(true);try{const job=await api('/api/generate',{prompt:$('gen-prompt').value,style:$('gen-style').value,steps:+$('gen-steps').value,guidance:+$('gen-guidance').value,seed:+$('gen-seed').value});const result=await pollJob(job.id);$('gen-status').textContent=result.message;$('gen-preview').src='/library/'+result.asset+'.png';$('gen-preview').hidden=false;$('gen-add').hidden=false;$('gen-add').onclick=safe(()=>addAsset(result.asset));await assets()}finally{setBusy(false)}});
async function init(){const status=await api('/api/status');token=status.token;$('ready').textContent=`محلي · ${status.illustrations} رسومات · ${status.assets-status.illustrations} رموز`;$('model-status').textContent=status.model.ready?'النموذج المحلي جاهز':'المخطط السريع جاهز؛ النموذج غير مشغّل';setBusy(false);await assets()}
setBusy(true);safe(init)();
/* ---- the rasm engine panel: why a render would be refused, and the resume ---- */
function prodStatus(data){
  const box=$('prod-status');box.replaceChildren();
  const head=el('div',undefined,'scene-head');
  head.append(el('b',data.family?('?????: '+data.family):'??? ???'));
  head.append(el('small',data.plan||'??? ??? ????'));
  box.append(head);
  const rows=(data.approvals&&(data.approvals.rows||data.approvals.assets))||data.approvals||[];
  const list=Array.isArray(rows)?rows:[];
  if(list.length){
    const ul=el('div');
    list.forEach(r=>ul.append(el('p',`${r.state||'?'} ? ${r.path||''}${r.in_plan?' ? ??????':''}`)));
    box.append(el('p','??????????:'),ul);
  }
  if(data.scenes&&data.scenes.length){
    const ul=el('div');
    data.scenes.forEach(s=>ul.append(el('p',`???? ${s.id} ? ${s.role||''} ? ${s.seconds||0}? ? ????? ${s.drawn_words??'?'} / ??? ${s.capacity_words??'?'} ${s.fits===false?'?':''}`)));
    box.append(el('p',`??????? ????: ${data.scenes_over_budget||0} ???? ???? ?????????`),ul);
  }
  if(data.parts&&data.parts.scenes_done){
    box.append(el('p',`???? ???? ?????????: ${data.parts.scenes_done} ???? ????`));
  }
}
$('prod-check').onclick=safe(async()=>{
  const pid=$('prod-project').value.trim();
  if(!pid)throw Error('???? ????? ????? ????');
  const res=await api('/api/rasm/status',{project_id:pid});
  prodStatus(res.status);
  toast('???? ??????? ??????');
});
$('prod-render').onclick=safe(async()=>{
  const pid=$('prod-project').value.trim();
  if(!pid)throw Error('???? ????? ????? ????');
  const res=await api('/api/rasm/render',{project_id:pid,mode:'final',size:[1280,720]});
  toast(res.ok?'????? ??????? ???????':'???? ???????');
  const box=$('prod-status');box.replaceChildren();
  box.append(el('p',res.ok?('? ????? ??????: '+res.path):('? '+(res.error||'????'))));
});
