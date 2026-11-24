"""Project model and versioned review workflow. One local creator, one generation worker."""
import copy, json, os, re, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import engine as e
lock=threading.RLock()
pool=ThreadPoolExecutor(1)
P=e.DATA/"projects";P.mkdir(exist_ok=True)
J=e.DATA/"jobs";J.mkdir(exist_ok=True)
def save(path,obj):
    temp=path.with_suffix(".tmp");temp.write_text(json.dumps(obj,ensure_ascii=False));os.replace(temp,path)
def read(path):return json.loads(path.read_text())
def path(folder,id):
    if not re.fullmatch("[0-9a-f]{32}",id):raise ValueError("编号无效")
    return folder/(id+".json")
def project(i):return read(path(P,i))
def store(p):p["updated"]=time.time();save(path(P,p["id"]),p)
def new(name):
    p={"schema":1,"aspect":"9:16","id":e.uid(),"name":name or "未命名剧集","script":"","cards":{},"order":[],"defaults":{k:"local" for k in ("text","image","video","audio")},"mix":{"subs":True,"speech":1,"effects":.45,"music":.18},"film":"","history":[]}
    store(p);return p
def card(kind,data):return {"kind":kind,"data":data,"state":"待生成","uri":"","version":0,"note":"","job":"","history":[]}
TIME_GROUPS = {
    "白天": {"白天","日间","白昼","清晨","早晨","早上","上午","中午","午后","下午","day","daytime","morning","afternoon"},
    "黄昏": {"黄昏","傍晚","日落","薄暮","夕阳时分","dusk","sunset","twilight"},
    "夜晚": {"夜晚","晚上","夜间","夜里","深夜","半夜","午夜","夜","night","midnight"},
}
def scene_key(row,label):
    loc=row.get("location")
    if not isinstance(loc,str) or not loc.strip():raise ValueError(f"{label}缺少地点 location")
    raw=str(row.get("time","")).strip().lower()
    for time,aliases in TIME_GROUPS.items():
        if raw in aliases:return loc.strip(),time
    raise ValueError(f"{label}「{loc}」的时间 {raw[:40]!r} 无法归类；需要白天、黄昏或夜晚")
def build(plan):
    cards={};order=[];chars={};scenes={}
    for x in plan["characters"]:
        n=str(x["name"]).strip()
        if n and n not in chars:
            k="C"+str(len(chars)+1);chars[n]=k;cards[k]=card("char",{"name":n,"look":x["look"],"outfit":x["outfit"],"voice":""})
    for x in plan["scenes"]:
        loc,t=scene_key(x,"场景")
        k=scenes.get((loc,t)) or "L"+str(len(scenes)+1);scenes[loc,t]=k;cards[k]=card("scene",{"location":loc,"time":t,"environment":x["environment"]})
    for i,x in enumerate(plan["shots"],1):
        k="S"+str(i);key=scene_key(x,f"镜头 {i}")
        if key not in scenes:raise ValueError(f"镜头 {i} 引用了未定义的场景：{key[0]}（{key[1]}）")
        loc=scenes[key];cast=[chars[n] for n in x["characters"]];lines=x["dialogue"]
        if not isinstance(lines,list):raise ValueError("对白必须按行存储")
        dialogue="\n".join(str(l["speaker"])+"："+str(l["text"]) for l in lines)
        seconds=min(15,max(1,float(x.get("seconds",5)),min(15,sum(len(str(l["text"])) for l in lines)/4)))
        cards[k]=card("shot",{"action":x["action"],"cast":cast,"scene":loc,"seconds":round(seconds,1),"dialogue":dialogue})
        cards[k]["state"]="待审核";order.append(k)
        for suffix,kind in (("F","frame"),("V","video"),("A","audio")):cards[k+suffix]=card(kind,{"shot":k})
        cards[k+"V"]["data"].update(start=0,end=round(seconds,1),sfx="")
    if not order:raise ValueError("模型未返回镜头")
    return cards,order
SCHEMA='你是竖屏漫剧导演。拆成约一分钟的镜头，每镜1–15秒，估算台词时长，过长拆镜。只输出如下结构：{"characters":[{"name":"角色名","look":"外貌","outfit":"服装"}],"scenes":[{"location":"纯地点","time":"黄昏","environment":"空镜环境、光线，无角色动物或剧情"}],"shots":[{"location":"引用地点","time":"对应时间","characters":["引用角色名"],"action":"可见动作、景别、构图、运镜，不含任何台词或文字","seconds":5,"dialogue":[{"speaker":"角色名或旁白","text":"台词"}]}]}。time 字段只能是白天、黄昏、夜晚中的一个值。镜头的 location、time 必须逐字复制对应场景的值。相同地点和时间复用，每个角色唯一。'
def plan_story(cfg,script,cap,repairing):
    instruction=SCHEMA+f"当前视频服务最长 {cap} 秒。优先 6–8 镜，字段简洁，不要重复原文。"
    prompt=script
    for attempt in range(2):
        raw=None
        try:
            raw=e.plan(cfg,prompt,instruction)
        except e.ModelFormatError as exc:
            reason=str(exc);draft=exc.reply
        else:
            try:
                result=build(raw)
                if any(result[0][s]["data"]["seconds"]>cap for s in result[1]):raise ValueError("拆镜结果超过视频时长限制")
                return result
            except (ValueError,KeyError,TypeError,AttributeError) as exc:
                reason=str(exc);draft=json.dumps(raw,ensure_ascii=False)
        if attempt or cfg["mode"]!="local":
            raise ValueError(("自动修复后仍无法拆镜：" if attempt else "拆镜格式错误：")+reason)
        repairing()
        prompt=json.dumps({"原文":script,"校验错误":reason,"待修复的输出":draft[:10000]},ensure_ascii=False)
        instruction+="修复所给草稿，返回完整合法 JSON 对象，补全缺失字段和括号，不要解释。"

def dependencies(p,k):
    c=p["cards"][k];d=c["data"];s=d.get("shot","")
    if c["kind"]=="frame":
        sh=p["cards"][s]["data"];return [s,sh["scene"],*sh["cast"]]
    if c["kind"]=="video":return [s+"F"]
    if c["kind"]=="audio":return [s]
    return []
def stale(p,keys):
    seen=set()
    while keys:
        k=keys.pop()
        if k in seen:continue
        seen.add(k);c=p["cards"][k];c["state"]="上游已更新";c["job"]=""
        keys.extend(n for n in p["cards"] if k in dependencies(p,n))
    p["film"]="";p["preview"]=""
def down(p,k):stale(p,[n for n in p["cards"] if k in dependencies(p,n)])
def edit(p,k,d):
    c=p["cards"][k];old=c["data"];d={**old,**{i:v for i,v in d.items() if i in old}}
    if old==d:return
    changes={i for i in old if old[i]!=d[i]}
    for i in changes:c.get("reviewed",{}).pop(i,None)
    if c["kind"]=="shot":
        if d["scene"] not in p["cards"] or p["cards"][d["scene"]]["kind"]!="scene" or not isinstance(d["cast"],list) or any(p["cards"].get(a,{}).get("kind")!="char" for a in d["cast"]):raise ValueError("角色或场景引用无效")
        if not 1<=float(d["seconds"])<=15:raise ValueError("镜头时长须为1–15秒")
    if c["kind"]=="scene" and d["time"] not in ("白天","黄昏","夜晚"):raise ValueError("请选择白天、黄昏或夜晚")
    if c["kind"]=="video" and not 0<=float(d["start"])<float(d["end"])<=p["cards"][d["shot"]]["data"]["seconds"]:raise ValueError("裁剪区间超出镜头时长")
    c["history"].append({"data":old,"uri":c["uri"],"version":c["version"],"at":time.time()});c["data"]=d;c["version"]+=1;p["film"]="";p["preview"]=""
    if c["kind"]=="video":return
    if changes=={"voice"}:
        stale(p,[s+"A" for s in p["order"] if k in p["cards"][s]["data"]["cast"]]);return
    c["job"]="";c["state"]="待审核" if c["kind"]=="shot" else "需修改"
    if changes=={"dialogue"}:stale(p,[k+"A"])
    else:down(p,k)
    if "seconds" in changes:p["cards"][k+"V"]["data"].update(start=0,end=d["seconds"])
def visual(text,dialogue):
    for line in dialogue.splitlines():
        phrase=line.split("：",1)[-1].strip()
        if phrase:text=text.replace(phrase,"")
    return re.sub(r'“[^”]*”|「[^」]*」','',text)
def config(kind,mode):
    f=e.DATA/"connections.json";cfg=read(f) if f.exists() else {}
    return {**cfg.get(kind,{}).get(mode,{}),"mode":mode}
def jobs(pid):return sorted([j for f in J.glob("*.json") if (j:=read(f))["pid"]==pid],key=lambda j:j["created"],reverse=True)
def submit(p,k,mode="",retry="",note=""):
    pid=p["id"];cards=p["cards"];c=cards.get(k);old=next((j for j in jobs(pid) if j["target"]==k and j["state"] in ("排队中","生成中")),None)
    if old:return old
    if c:
        for dep in dependencies(p,k):
            if cards[dep]["state"]!="已确认":raise ValueError("请先确认 "+dep)
    elif k not in ("plan","film","preview") and not k.startswith("sample:"):raise ValueError("未知任务")
    if k=="film" and (not p["order"] or any(cards[s+"V"]["state"]!="已确认" or cards[s]["state"]!="已确认" for s in p["order"])):raise ValueError("请先确认所有分镜和视频")
    if k=="preview" and (not p["order"] or any(not cards[s+"V"]["uri"] for s in p["order"])):raise ValueError("预览需要每个镜头都有视频")
    kind={"char":"image","scene":"image","frame":"image","video":"video","audio":"audio"}.get((c or {}).get("kind"),"text")
    if k.startswith("sample:"):kind=k.split(":")[1]
    mode=mode or p["defaults"].get(kind,"local")
    if mode not in ("local","api") or kind not in ("text","image","video","audio"):raise ValueError("无效生成服务")
    if retry:
        j=read(path(J,retry))
        if j["pid"]!=pid or j["target"]!=k or j["state"]!="失败":raise ValueError("任务不可重试")
        if c and j["version"]!=c["version"]:raise ValueError("素材已经修改，请新建任务")
        if j.get("uncertain") and not j.get("remote"):raise ValueError("上次远程提交状态未知。请在供应商端核对后再新建任务。")
    else:j={"id":e.uid(),"pid":pid,"target":k,"kind":kind,"mode":mode,"created":time.time(),"version":(c or {}).get("version",0),"note":note}
    connection=config(kind,mode if not retry else j["mode"])
    public={f:connection.get(f,"") for f in ("url","model","query","voice","maxSeconds","mode")}
    if not retry:j["connection"]=public
    elif j.get("remote") and j.get("connection",public)!=public:raise ValueError("原任务的接口或模型已改变，请恢复原配置再查询")
    j.update(state="排队中",phase="等待执行",error="")
    if c:
        down(p,k);c.update(job=j["id"],state="生成中",note=j["note"])
    save(path(J,j["id"]),j);store(p);pool.submit(work,j["id"]);return j
def work(id):
    jp=path(J,id)
    def check():
        if read(jp)["state"]=="已取消":raise ValueError("已取消")
    def update(**kw):
        with lock:
            check();j=read(jp);j.update(kw);save(jp,j);return j
    def ticket(*value):
        if value:update(remote=value[0],uncertain=False,phase="等待远程结果")
        return read(jp).get("remote")
    ticket.id=id
    try:
        j=update(state="生成中",phase="调用生成服务");pid=j["pid"];k=j["target"];p=project(pid);cards=p["cards"];c=cards.get(k,{});d=c.get("data",{});s=d.get("shot");sh=cards[s]["data"] if s else {};kind=j["kind"];cfg=config(kind,j["mode"]);cfg.update(j.get("connection",{}));refs=[];note=j["note"];out="";detail=""
        if k=="plan":
            if not p["script"].strip():raise ValueError("请先输入剧本")
            cap=float(config("video",p["defaults"]["video"]).get("maxSeconds") or 15)
            result=plan_story(cfg,p["script"],cap,lambda:update(phase="正在修复分镜格式"))
        elif k in ("film","preview"):
            clips=[]
            for s in p["order"]:
                sh=cards[s]["data"];v=cards[s+"V"];a=cards[s+"A"]
                if k=="film" and a["uri"] and a["state"]!="已确认":raise ValueError("请复审配音："+s)
                clips.append({**sh,**v["data"],"video":v["uri"],"audio":a["uri"]})
            out=e.render(clips,p["mix"],check)
        elif k.startswith("sample:") and kind=="text":detail=e.plan(cfg,"测试","输出 JSON 对象，字段 ready 为 true");out=""
        else:
            sec=sh.get("seconds",2);wide=c.get("kind")=="char";voice=""
            if k.startswith("sample:"):
                prompt="A red apple on a plain table" if kind!="audio" else "漫剧工作台试听。"
                if kind in ("image","video"):
                    import base64
                    # Generate a real portrait test frame using FFmpeg.
                    f=e.target("png");e.run([e.FF,"-y","-f","lavfi","-i","color=c=navy:s=288x512","-frames:v",1,f],check);refs=[e.uri(f)]
            elif wide:prompt="Comic character turnaround: full body FRONT, SIDE, BACK of the same character, plain background, no labels. "+json.dumps({a:d[a] for a in ("name","look","outfit")},ensure_ascii=False)
            elif c["kind"]=="scene":prompt="Single unoccupied comic environment. No people, animals, silhouettes, lettering or panels. "+json.dumps(d,ensure_ascii=False)
            elif c["kind"]=="frame":
                refs=[cards[x]["uri"] for x in sh["cast"]+[sh["scene"]]]
                prompt="Single 9:16 comic shot. Preserve characters in reference order; last image is environment. No captions, letters or speech bubbles. "+sh["action"]
            elif kind=="video":
                if sec>float(cfg.get("maxSeconds") or 15):raise ValueError("时长超过本次视频接口限制，请拆镜或缩短")
                refs=[cards[s+"F"]["uri"]];prompt="Animate the supplied first frame, preserve identity. No text or subtitles. "+sh["action"]
            else:
                lines=sh["dialogue"].splitlines()
                if not lines:raise ValueError("此镜头没有对白或旁白")
                paths=[]
                for line in lines:
                    speaker,sep,text=line.partition("：");voice=next((v["data"]["voice"] for v in cards.values() if v["kind"]=="char" and v["data"]["name"]==speaker),"") or cfg.get("voice","")
                    paths.append(e.file(e.generate("audio",cfg,text if sep else line,[],0,voice,ticket,check)))
                f=e.target("wav");cmd=[e.FF,"-y"]
                for a in paths:cmd+=["-i",a]
                e.run(cmd+["-filter_complex","".join(f"[{i}:a]" for i in range(len(paths)))+f"concat=n={len(paths)}:v=0:a=1","-ar",44100,f],check);out=e.uri(f)
            if not out:
                if sh and kind in ("image","video"):prompt=visual(prompt,sh["dialogue"]);note=visual(note,sh["dialogue"])
                if kind in ("image","video") and cfg["mode"]=="api" and not ticket():update(uncertain=True)
                update(params={"kind":kind,"mode":cfg["mode"],"model":cfg.get("model",""),"duration":sec,"references":refs,"prompt":prompt,"feedback":note})
                out=e.generate(kind,cfg,prompt+("。修改要求："+note if note else ""),refs,sec,voice,ticket,check,wide)
        with lock:
            check();now=project(pid)
            if k=="plan":
                if p["script"]!=now["script"]:raise ValueError("原文已更新，请重新拆镜")
                if now["cards"]:now["history"].append({"cards":now["cards"],"order":now["order"],"at":time.time()})
                now["cards"],now["order"]=result;now["film"]="";now["preview"]=""
            elif k in ("film","preview"):
                if p["cards"]!=now["cards"] or p["mix"]!=now["mix"] or p["order"]!=now["order"]:raise ValueError("时间轴已更新，请重新导出")
                now["film" if k=="film" else "preview"]=out
            elif c:
                cur=now["cards"][k]
                if cur["job"]!=id:raise ValueError("上游已更新，结果未覆盖当前版本")
                cur["history"].append({"uri":cur["uri"],"data":d,"version":cur["version"]})
                cur["params"]=read(jp).get("params",{"kind":kind,"mode":cfg["mode"],"model":cfg.get("model","")});cur.update(uri=out,version=cur["version"]+1,state="待审核",job="")
            store(now);update(state="完成",uri=out,detail=detail,refs=refs,uncertain=False)
    except Exception as exc:
        with lock:
            j=read(jp);now=project(j["pid"]);c=now["cards"].get(j["target"])
            if c and c["job"]==id:c.update(state="失败",job="");store(now)
            if j["state"]!="已取消":update(state="失败",error=str(exc)[:1800])
def recover():
    for f in J.glob("*.json"):
        j=read(f)
        if j["state"] in ("排队中","生成中"):
            if j["state"]=="排队中" or j.get("remote"):pool.submit(work,j["id"])
            else:
                j.update(state="失败",error="服务已重启；请检查原请求状态");save(f,j)
                p=project(j["pid"]);c=p["cards"].get(j["target"])
                if c and c["job"]==j["id"]:c.update(state="失败",job="");store(p)
