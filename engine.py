"""Local generation adapters and a documented JSON gateway for external providers."""
import base64, json, os, re, shutil, subprocess, tempfile, time, urllib.request
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parent
DATA=Path(os.getenv("STUDIO_DATA",ROOT/"data")).resolve()
MEDIA=DATA/"media"
MEDIA.mkdir(parents=True,exist_ok=True)
H3=Path(os.getenv("H3_RUNTIME",ROOT.parent/"h3-runtime"))
IMG=Path(os.getenv("H3_IMAGE_RUNTIME",ROOT.parent/"h3-image-runtime"))
FF=os.getenv("FFMPEG") or shutil.which("ffmpeg") or str(H3/".venv/bin/ffmpeg")
def uid(): return uuid4().hex
def file(uri):
    if not re.fullmatch(r'/media/[a-f0-9]{32}\.(png|jpg|webp|mp4|wav|mp3|m4a|aiff)',uri): raise ValueError("素材路径无效")
    p=MEDIA/uri[7:]
    if not p.is_file(): raise ValueError("素材不存在："+p.name)
    return p
def target(ext): return MEDIA/(uid()+"."+ext)
def uri(p): return "/media/"+p.name
def req(url,body=None,key="",raw=False,headers=None):
    if not url.startswith(("http://","https://")): raise ValueError("需要 HTTP(S) 接口地址")
    h={"Content-Type":"application/json",**(headers or {})}
    if key:h["Authorization"]="Bearer "+key
    r=urllib.request.Request(url,None if body is None else json.dumps(body).encode(),h)
    with urllib.request.urlopen(r,timeout=900) as f:return f.read() if raw else json.load(f)
def inline(u):
    import mimetypes
    p=file(u);return "data:"+mimetypes.guess_type(p.name)[0]+";base64,"+base64.b64encode(p.read_bytes()).decode()
def media_result(res,ext):
    obj=res.get("data",res)
    if isinstance(obj,list):obj=obj[0]
    url=obj.get("url") or obj.get("video_url") or obj.get("audio_url")
    data=base64.b64decode(obj["b64_json"],validate=True) if obj.get("b64_json") else (base64.b64decode(url.split(",",1)[1],validate=True) if url and url.startswith("data:") else req(url or "",raw=True))
    if not data:raise ValueError("接口返回空素材")
    if ext=="png":
        if data.startswith(b'\xff\xd8'):ext="jpg"
        elif data[:4]==b'RIFF':ext="webp"
        elif not data.startswith(b'\x89PNG'):raise ValueError("返回值不是 PNG/JPEG/WebP")
    p=target(ext);p.write_bytes(data);return uri(p)
def run(args,check=lambda:None,cwd=None):
    with tempfile.TemporaryFile() as log:
        proc=subprocess.Popen([str(i) for i in args],cwd=cwd,stdout=log,stderr=log,env={**os.environ,"PATH":str(H3/".venv/bin")+os.pathsep+os.getenv("PATH","")})
        try:
            while proc.poll() is None:check();time.sleep(.25)
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
        if proc.returncode:
            log.seek(0);raise ValueError(log.read().decode(errors="replace")[-1500:] or "外部程序失败")
def plan(cfg,story,instruction):
    msgs=[{"role":"system","content":instruction+"。仅返回合法 JSON，不要 Markdown。"},{"role":"user","content":story}]
    if cfg["mode"]=="local":
        # Some Ollama MLX builds lack xgrammar and reject format=json with HTTP 501.
        # Request JSON in the system prompt and enforce it in the parser below.
        data=req(cfg.get("url") or "http://127.0.0.1:11434/api/chat",{"model":cfg.get("model") or "qwen3.5:4b","messages":msgs,"think":False,"stream":False,"keep_alive":0})
        out=data["message"]["content"]
    else:out=req(cfg["url"],{"model":cfg["model"],"messages":msgs,"response_format":{"type":"json_object"}},cfg.get("key"))["choices"][0]["message"]["content"]
    try:
        result=json.loads(re.sub(r'^\s*```(?:json)?|```\s*$','',out.strip()))
    except json.JSONDecodeError as exc:
        raise ValueError(f"文本模型已连接，但没有返回合法 JSON（第 {exc.lineno} 行）；请重试。") from exc
    if not isinstance(result,dict):raise ValueError("文本模型已连接，但返回的不是 JSON 对象。")
    return result
def generate(kind,cfg,prompt,refs,duration,voice,ticket,check,wide=False):
    w,h=(1536,1024) if wide else (576,1024)
    if cfg["mode"]=="api":
        payload={"model":cfg["model"],"prompt":prompt}
        if kind=="image":payload.update(width=w,height=h,n=1,reference_images=[inline(u) for u in refs])
        if kind=="video":payload.update(first_frame_image=inline(refs[0]),duration=duration,aspect_ratio="9:16")
        if kind=="audio":
            audio=req(cfg["url"],{"model":cfg["model"],"input":prompt,"voice":voice or "alloy","response_format":"mp3"},cfg.get("key"),True)
            p=target("mp3");p.write_bytes(audio);return uri(p)
        job=ticket()
        if not job:
            res=req(cfg["url"],payload,cfg.get("key"),headers={"Idempotency-Key":ticket.id})
            job=res.get("task_id")
            if not job:return media_result(res,"png" if kind=="image" else "mp4")
            ticket(job)
        from urllib.parse import quote
        if "{id}" not in cfg.get("query",""):raise ValueError("请配置含 {id} 的任务查询地址，已保存原任务号")
        for _ in range(3600):
            check();res=req(cfg["query"].replace("{id}",quote(str(job),safe="")),key=cfg.get("key"))
            status=res.get("status")
            if status in ("succeeded","success","completed"):return media_result(res,"png" if kind=="image" else "mp4")
            if status in ("failed","cancelled","canceled"):ticket("");raise ValueError("供应商任务失败："+str(res.get("error","")))
            time.sleep(2)
        raise ValueError("查询超时，可继续查询原任务")
    if kind=="image":
        p=target("png")
        cmd=[IMG/".venv/bin/h3-image-mlx","generate","--models",IMG/"models","--dit-mode","stream","--width",w,"--height",h,"--prompt",prompt,"--output",p]
        for u in refs:cmd+=["--reference",file(u)]
        run(cmd,check)
    elif kind=="video":
        p=target("mp4")
        run([H3/".venv/bin/python","scripts/generate.py",prompt,"--checkpoint","models/MiniMax-H3/FL2VA","--transformer","models/MiniMax-H3/FL2VA/transformer","--turbo-lora","models/turbo/minimax_h3_fl2v_turbo_4step_v1.0_768p_bf16.safetensors","--sigma-shift-video",6,"--sigma-shift-audio",3,"--low-memory","--stream-blocks","--stream-block-group-size",1,"--no-block-cache","--resolution","288x512","--aspect",9,16,"--image",file(refs[0]),"--anchor","first","--duration",duration,"--steps",5,"--memory-limit-gb",20,"--require-muxed-mp4","--output",p],check,H3)
    else:
        p=target("aiff");run(["say",*(["-v",voice] if voice else []),"-o",p,"--",prompt],check)
    if not p.exists() or not p.stat().st_size:raise ValueError("没有生成有效文件")
    return uri(p)
def render(shots,opts,check):
    with tempfile.TemporaryDirectory() as tmp:
        parts=[]
        for i,s in enumerate(shots):
            check();duration=float(s["end"])-float(s["start"])
            args=[FF,"-y","-ss",s["start"],"-i",file(s["video"])]
            vf="scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,tpad=stop_mode=clone:stop_duration=15"
            lines=s["dialogue"].splitlines()
            if opts.get("subs",True) and lines:
                def stamp(x):
                    ms=int(x*1000);return f"00:{ms//60000:02}:{ms//1000%60:02},{ms%1000:03}"
                # Subtitle timing follows original shot time, clipped to the selected interval.
                entries=[]
                for j,line in enumerate(lines):
                    a=max(0,j*s["seconds"]/len(lines)-s["start"]);b=min(duration,(j+1)*s["seconds"]/len(lines)-s["start"])
                    if b>a:entries.append(f"{len(entries)+1}\n{stamp(a)} --> {stamp(b)}\n{line}\n")
                if entries:
                    Path(tmp,"sub.srt").write_text("\n".join(entries));vf+=",subtitles=sub.srt:force_style='FontName=PingFang SC,FontSize=13,MarginV=23,Outline=1'"
            inputs=[];filters=[]
            for track,gain,loop in [(s.get("audio"),opts.get("speech",1),False),(s.get("sfx"),opts.get("effects",.45),False),(opts.get("bgm"),opts.get("music",.18),True)]:
                if track:
                    args+=(["-stream_loop","-1"] if loop else [])+["-ss",sum(parts) if loop else s["start"],"-i",file(track)]
                    n=len(inputs)+1;filters.append(f"[{n}:a]volume={max(0,min(2,float(gain)))},apad[a{n}]");inputs.append(f"[a{n}]")
            if inputs:args+=["-filter_complex",";".join(filters+["".join(inputs)+f"amix=inputs={len(inputs)}:normalize=0[out]"]),"-map","[out]"]
            else:args+=["-f","lavfi","-i","anullsrc=r=44100:cl=stereo","-map","1:a"]
            run(args+["-map","0:v:0","-vf",vf,"-t",duration,"-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p","-c:a","aac","-ar",44100,"-ac",2,f"{i}.mp4"],check,tmp);parts.append(duration)
        Path(tmp,"list").write_text("".join(f"file '{i}.mp4'\n" for i in range(len(parts))))
        p=target("mp4");run([FF,"-y","-f","concat","-safe",0,"-i","list","-c","copy","-movflags","+faststart",p],check,tmp);return uri(p)
