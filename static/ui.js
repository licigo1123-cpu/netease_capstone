'use strict';
const $=s=>document.querySelector(s), E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),tabs=['剧本与分镜','角色设定','场景环境','镜头关键帧','镜头视频','声音与剪辑','任务记录'],types={text:'文本 LLM',image:'图片生成',video:'视频生成',audio:'角色配音'}, names={action:'画面动作 · 不含对白',dialogue:'独立对白 · 每行「角色：台词」',cast:'出镜角色',scene:'场景',seconds:'预计时长（秒）',name:'角色名',look:'外貌设定',outfit:'服装设定',voice:'固定音色（空白使用默认音色）',location:'具体地点',time:'时间',environment:'环境与光线',start:'裁剪起点（秒）',end:'裁剪终点（秒）'};
let P,J=[],tab=0,timer,settings={},serial=Promise.resolve(),pending=0,polling=false,revision=0;
const btn=(a,t,k='',cl='')=>'<button class="'+cl+'" data-a="'+a+'" data-k="'+E(k)+'">'+t+'</button>';
const option=(v,t,sel)=>'<option value="'+E(v)+'" '+(v===sel?'selected':'')+'>'+E(t)+'</option>';
const url=u=>/^\/media\/[a-f0-9]{32}\.(png|jpg|webp|mp4|wav|mp3|m4a|aiff)$/.test(u)?E(u):'';
const media=u=>!url(u)?'':(/\.mp4$/.test(u)?'<video controls playsinline src="'+url(u)+'"></video>':/\.(mp3|wav|aiff|m4a)$/.test(u)?'<audio controls src="'+url(u)+'"></audio>':'<img loading="lazy" src="'+url(u)+'">');
function msg(t){$('#toast').textContent=t;clearTimeout(timer);timer=setTimeout(()=>$('#toast').textContent='',5000);if($('dialog').open){$('#notice').textContent=t}}
async function request(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw Error(d.error||r.status);return d}
const api=(act,b={})=>request('/api',{id:P?.id,act,...b});
async function refresh(draw=true){let id=P.id;const d=await request('/project?id='+id);if(P.id!==id)return;P=d.p;J=d.jobs;if(draw)render()}
function mode(k,kind){return '<select aria-label="本次生成服务" id="m'+k+'">'+option('','项目默认 · '+(P.defaults[kind]==='api'?'API':'本地'),'')+option('local','本地服务')+option('api','自定义 API')+'</select>'}
function field(k,f,v){let input;const attrs=' data-card="'+k+'" data-f="'+f+'"';
 if(f==='cast')input=Object.entries(P.cards).filter(([,c])=>c.kind==='char').map(([id,c])=>'<label><input style="width:auto" type="checkbox" '+attrs+' value="'+id+'" '+(v.includes(id)?'checked':'')+'>'+E(c.data.name)+'</label>').join('')||'无角色';
 else if(f==='scene'||f==='time')input='<select'+attrs+'>'+(f==='time'?['白天','黄昏','夜晚'].map(t=>option(t,t,v)):Object.entries(P.cards).filter(([,c])=>c.kind==='scene').map(([id,c])=>option(id,c.data.location+' · '+c.data.time,v))).join('')+'</select>';
 else if(typeof v==='number')input='<input type="number" step=".1"'+attrs+' value="'+v+'">';
 else input='<textarea'+attrs+'>'+E(v)+'</textarea>';
 return '<div class="field '+f+'"><label>'+E(names[f]||f)+'</label>'+input+(P.cards[k]?.kind==='shot'?btn('fieldreview',P.cards[k].reviewed?.[f]?'✓ 已核对':'核对此项',k+':'+f):'')+'</div>'}
function card(k){const c=P.cards[k],d=c.data,kind=c.kind,shot=P.cards[d.shot]?.data,isShot=kind==='shot';let content='';
 if(['char','scene','shot'].includes(kind))content=Object.entries(d).map(([f,v])=>field(k,f,v)).join('');
 if(shot)content='<p>'+E(shot.action)+'</p>'+content;
 if(kind==='frame')content+='<p class="note">参考素材：'+[...shot.cast,shot.scene].map(n=>E(P.cards[n].data.name||P.cards[n].data.location)).join('、')+'</p>';
 if(kind==='audio')content+='<p>'+E(shot.dialogue||'本镜无对白，可跳过配音。').replaceAll('\n','<br>')+'</p>';
 let refine=['char','scene','shot'].includes(kind)?'<div class="row"><select id="f'+k+'">'+Object.keys(d).filter(f=>['look','outfit','environment','location','action','dialogue','cast','scene'].includes(f)).map(f=>option(f,names[f])).join('')+'</select>'+btn('refine','按意见细化字段',k)+'</div>':'';
 return '<article><div class="meta"><label>'+E(k)+' · '+E(({frame:'关键帧',video:'镜头视频',audio:'配音',shot:'分镜',char:d.name,scene:d.location})[kind])+'</label><b class="badge">'+E(c.state)+' · v'+E(c.version)+'</b></div>'+content+media(c.uri)+'<details><summary>修改建议与版本记录</summary><textarea id="n'+k+'" placeholder="例如：保持外套颜色，把镜头改为近景">'+E(c.note)+'</textarea>'+refine+'<p class="note">'+c.history.length+' 条历史记录</p>'+c.history.slice(-4).reverse().map(h=>url(h.uri)?'<a href="'+url(h.uri)+'" target="_blank">查看 v'+h.version+' 素材</a> ':'').join('')+'</details><div class="row">'+(isShot?'':mode(k,kind==='video'?'video':kind==='audio'?'audio':'image')+btn('gen','生成 / 重做',k,'primary'))+btn('approve','确认',k)+btn('reject','需修改',k)+'</div></article>'}
function intro(title,text){return '<div class="intro"><h2>'+title+'</h2><p>'+text+'</p></div>'}
function splitControls(){
 const active=J.find(j=>j.target==='plan'&&['排队中','生成中'].includes(j.state));
 const job=active||J.find(j=>j.target==='plan');
 const text=!job?'':job.state==='失败'?'拆镜失败：'+(job.error||'未返回错误详情'):job.state==='排队中'?'拆镜已排队，等待前面的任务结束。':job.phase==='正在修复分镜格式'&&job.state==='生成中'?'模型首次输出未通过校验，正在自动修复一次。':job.state==='生成中'?'文本模型正在拆分剧本，完成后会自动显示分镜卡，无需重复点击。':job.state==='完成'?'拆镜完成：'+P.order.length+' 个镜头。':'拆镜已取消。';
 return '<div class="row">'+mode('plan','text')+(active?'<button disabled>'+E(active.state)+'…</button>':btn('gen','拆分剧本','plan','primary'))+'</div><div role="status">'+E(text)+'</div>';
}
function render(){
 $('#tabs').innerHTML=tabs.map((t,i)=>btn('tab','0'+(i+1)+'　'+t,i,tab===i?'active':'')).join('');
 $('#title').textContent=P.name;$('#sync').textContent='9:16　·　'+P.order.length+' 镜　·　'+(J.some(j=>['排队中','生成中'].includes(j.state))?'任务执行中':'已保存');
 let h='',kind=['shot','char','scene','frame','video'][tab];
 if(tab===0)h=intro('从一段故事开始','粘贴剧本，拆出镜头、角色、场景与独立对白。先复核分镜，再制作素材。')+'<article><label>剧本原文</label><textarea id="script" style="min-height:145px" placeholder="在这里输入故事或小说片段…">'+E(P.script)+'</textarea>'+splitControls()+'</article>';
 if(tab>0&&tab<5)h=intro(tabs[tab],['','每个角色共用一张正、侧、背三视图；审核后可供多个镜头引用。','同一地点和时间复用一张空镜图。先核对结构化环境字段，再生成。','按镜头绑定已确认的角色三视图与场景图。','复用已确认关键帧补拍单镜。'][tab]);
 if(kind){const keys=Object.keys(P.cards).filter(k=>P.cards[k].kind===kind);h+='<div class="grid">'+keys.map(card).join('')+'</div>';if(!keys.length)h+='<p class="note">暂无卡片。完成剧本拆分后将在这里出现。</p>'}
 if(tab===5){
 h=intro('声音与剪辑','按顺序裁剪镜头、试听配音。导出时烧录独立字幕，混合人声、配乐和音效。')+'<article><label>BGM 音轨</label><input type="file" accept="audio/*" data-upload="bgm">'+media(P.mix.bgm)+'<div class="row">'+['speech','music','effects'].map((k,i)=>'<label>'+['人声','音乐','音效'][i]+' <input type="number" min="0" max="2" step=".05" data-mix="'+k+'" value="'+E(P.mix[k])+'"></label>').join('')+'<label><input type="checkbox" style="width:auto" data-mix="subs" '+(P.mix.subs?'checked':'')+'>烧录字幕</label></div></article>';
 for(const [i,s] of P.order.entries()){const v=P.cards[s+'V'];h+='<article><div class="row"><h3>镜头 '+(i+1)+' · '+s+'</h3>'+btn('up','↑',s)+btn('down','↓',s)+'</div>'+media(v.uri)+field(s+'V','start',v.data.start)+field(s+'V','end',v.data.end)+'<label>本镜音效</label><input type="file" accept="audio/*" data-upload="'+s+'V">'+media(v.data.sfx)+btn('preview','预览本镜字幕与配音',s)+'</article>'+card(s+'A')}
 h+='<article>'+btn('gen','预览完整时间轴','preview')+media(P.preview)+btn('gen','合成最终 MP4','film','primary')+media(P.film)+(url(P.film)?'<a download="漫剧.mp4" href="'+url(P.film)+'">下载最终视频</a>':'')+'</article>'}
 if(tab===6){h=intro('生成任务','刷新可恢复进度。远程任务有编号时，重试会继续查询原任务。')+J.map(j=>'<article><div class="meta"><b>'+E(j.target)+' · '+E(j.state)+'</b><label>'+E(j.mode)+'</label></div><p>'+E(j.error||[j.phase,j.remote].filter(Boolean).join(' · '))+'</p>'+(['排队中','生成中'].includes(j.state)?btn('cancel','停止',j.id):j.state==='失败'?btn('retry','重试 / 查询原任务',j.id):'')+(j.target.startsWith('sample:')?media(j.uri)+E(JSON.stringify(j.detail||'')):'')+'</article>').join('')}
 $('#view').innerHTML=h
}
function dlg(title,body){$('#dlgtitle').textContent=title;$('#panel').innerHTML='<p id="notice" class="error"></p>'+body;if(!$('dialog').open)$('dialog').showModal()}
async function projectMenu(){let rows=await request('/list');dlg('项目管理','<div class="row"><input id="newname" placeholder="新项目名称">'+btn('new','新建项目')+'</div>'+rows.map(r=>'<article class="row">'+(url(r.cover)?'<img class="mini" src="'+url(r.cover)+'">':'')+'<div><b>'+E(r.name)+'</b><p>'+new Date(r.updated*1000).toLocaleString()+' · 视频确认 '+r.approved+'/'+r.total+'</p></div>'+btn('open','打开',r.id)+'</article>').join(''))}
async function choose(id){P={id};localStorage.setItem('comic-project',id);tab=0;$('dialog').close();await refresh()}
async function configUI(){settings=await request('/settings');dlg('连接设置',Object.entries(types).map(([k,t])=>'<article><h3>'+t+'</h3><label>本项目默认服务</label><select data-default="'+k+'">'+option('local','本地',P.defaults[k])+option('api','自定义 API',P.defaults[k])+'</select>'+['local','api'].map(m=>{let d=settings[k]?.[m]||{};return '<details><summary>'+({api:'自定义 HTTP API',local:'本地 · '+({text:'Ollama / Qwen',image:'MiniMax H3 Image CLI',video:'MiniMax H3 CLI',audio:'macOS 系统语音'})[k]})[m]+'</summary>'+((m==='api'?['url','model','key',...(['image','video'].includes(k)?(k==='video'?['query','maxSeconds']:['query']):k==='audio'?['voice']:k==='video'?['maxSeconds']:[])]:k==='text'?['url','model']:k==='audio'?['voice']:[]).map(f=>'<label>'+({url:'完整请求地址',model:'模型',key:d.keySet?'密钥（已保存，留空保留）':'API 密钥',query:'任务查询 URL（用 {id} 指代任务号）',voice:'默认音色',maxSeconds:'单镜最长秒数（1–15）'})[f]+'<input data-cfg="'+k+':'+m+':'+f+'" type="'+(f==='key'?'password':'text')+'" value="'+E(d[f]||'')+'"></label>').join(''))+'<div class="row">'+btn('probe','测试连接',k+':'+m)+btn('sample','生成小样',k+':'+m)+'</div></details>'}).join('')+'</article>').join('')+btn('cfgsave','保存连接设置','','primary'))}
async function saveCfg(){let cfg={},defaults={};document.querySelectorAll('[data-cfg]').forEach(el=>{let [k,m,f]=el.dataset.cfg.split(':');((cfg[k]??={})[m]??={})[f]=el.value.trim()});document.querySelectorAll('[data-default]').forEach(el=>defaults[el.dataset.default]=el.value);await api('settings',{settings:cfg});await api('save',{data:{defaults}})}
function queue(fn){pending++;revision++;serial=serial.then(fn).catch(e=>msg(e.message)).finally(()=>pending--);return serial}
document.addEventListener('change',ev=>{const el=ev.target,{card:k,f,mix,upload}=el.dataset;if(!P)return;
 if(k){let value=f==='cast'?[...document.querySelectorAll('[data-card="'+k+'"][data-f="cast"]:checked')].map(i=>i.value):el.type==='number'?Number(el.value):el.value;queue(async()=>{P=await api('edit',{k,data:{[f]:value}});$('#sync').textContent='已自动保存'})}
 if(el.id==='script'){const script=el.value;queue(async()=>{P=await api('save',{data:{script}})})}
 if(mix){let val=el.type==='checkbox'?el.checked:Number(el.value);queue(async()=>{P=await api('save',{data:{mix:{...P.mix,[mix]:val}}})})}
 if(upload&&el.files[0])queue(async()=>{const f=el.files[0],r=await fetch('/upload?ext='+encodeURIComponent(f.name.split('.').pop().toLowerCase()),{method:'POST',body:f}),d=await r.json();if(d.error)throw Error(d.error);P=upload==='bgm'?await api('save',{data:{mix:{...P.mix,bgm:d.uri}}}):await api('edit',{k:upload,data:{sfx:d.uri}});render()});
 if(el.id==='zip'&&el.files[0])queue(async()=>{const d=await(await fetch('/import',{method:'POST',body:el.files[0]})).json();el.value='';if(d.error)throw Error(d.error);await choose(d.id)})
});
document.addEventListener('click',async ev=>{const b=ev.target.closest('[data-a]');if(!b)return;let {a,k}=b.dataset;b.disabled=true;try{await serial;const note=document.getElementById('n'+k)?.value||'';
 if(a==='close')return $('dialog').close();if(a==='settings')return await configUI();if(a==='projects')return await projectMenu();if(a==='open')return await choose(k);if(a==='new')return await choose((await api('new',{name:$('#newname').value})).id);
 if(a==='pack'){location.href='/package?id='+P.id;return}if(a==='import')return $('#zip').click();
 if(a==='tab'){tab=+k;return await refresh()}if(a==='cfgsave'){await saveCfg();$('dialog').close();msg('连接已保存');return await refresh()}
 if(a==='probe'||a==='sample'){await saveCfg();let [kind,mode]=k.split(':');if(a==='probe')return msg((await api('probe',{kind,mode})).message);await api('submit',{k:'sample:'+kind,mode});$('dialog').close();tab=6}
 if(a==='gen'){if(k==='plan'&&!P.script.trim())throw Error('请先输入剧本原文');if(k==='plan'&&(!P.script.trim()||P.order.length&&!confirm('重新拆镜将归档当前分镜和素材，继续？')))return;await api('submit',{k,mode:document.getElementById('m'+k)?.value,note});msg('已加入任务队列')}
 if(a==='fieldreview'){const [n,f]=k.split(':');await api('fieldreview',{k:n,field:f,note:document.getElementById('n'+n)?.value||''})}
 if(a==='reject'||a==='approve')await api('review',{k,state:a==='approve'?'已确认':'需修改',note});
 if(a==='refine'){if(!note.trim())throw Error('请先填写修改建议');await api('refine',{k,note,field:$('#f'+k).value})}
 if(a==='retry'||a==='cancel'){const j=J.find(j=>j.id===k);await api(a==='retry'?'submit':'cancel',{k:j.target,retry:k,job:k})}
 if(a==='up'||a==='down'){let order=P.order.slice(),i=order.indexOf(k),j=i+(a==='up'?-1:1);if(j>=0&&j<order.length){[order[i],order[j]]=[order[j],order[i]];await api('save',{data:{order}})}}
 if(a==='preview'){let v=P.cards[k+'V'],s=P.cards[k],au=P.cards[k+'A'];if(!v.uri)throw Error('请先生成镜头视频');dlg('镜头预览',media(v.uri)+'<p id="caption"></p>'+media(au.uri));let vid=$('#panel video'),audio=$('#panel audio'),lines=s.data.dialogue.split('\n');vid.muted=true;vid.onloadedmetadata=()=>vid.currentTime=v.data.start;vid.onplay=()=>{if(vid.currentTime>=v.data.end)vid.currentTime=v.data.start;if(audio){audio.currentTime=vid.currentTime;audio.volume=Math.min(1,P.mix.speech);audio.play().catch(()=>{})}};vid.onpause=()=>audio?.pause();vid.ontimeupdate=()=>{if(vid.currentTime>=v.data.end)vid.pause();$('#caption').textContent=P.mix.subs?lines[Math.min(lines.length-1,Math.floor(vid.currentTime/s.data.seconds*lines.length))]:''};return}
 await refresh()
 }catch(e){msg(e.message)}finally{b.disabled=false}});
$('dialog').addEventListener('close',()=>$('#panel').querySelectorAll('video,audio').forEach(x=>x.pause()));
(async()=>{try{const rows=await request('/list');await choose(rows.find(r=>r.id===localStorage.getItem('comic-project'))?.id||rows[0]?.id||(await api('new',{name:'我的第一集'})).id)}catch(e){msg(e.message)}})();
setInterval(async()=>{if(!P||polling||pending||$('dialog').open||document.activeElement?.matches('textarea,input,select')||!J.some(j=>['排队中','生成中'].includes(j.state)))return;polling=true;try{let id=P.id,v=revision,d=await request('/project?id='+id);if(P.id===id&&v===revision&&!document.activeElement?.matches('textarea,input,select')&&JSON.stringify(J)!==JSON.stringify(d.jobs)){P=d.p;J=d.jobs;render()}}catch(e){msg(e.message)}finally{polling=false}},1800);
