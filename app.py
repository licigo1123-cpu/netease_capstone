import argparse, io, json, mimetypes, re, shutil, socket, tempfile, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import engine as e, studio as st
from pathlib import Path
CFG=e.DATA/"connections.json"
def assets(p):
    if isinstance(p,dict):
        for v in p.values():yield from assets(v)
    elif isinstance(p,list):
        for v in p:yield from assets(v)
    elif isinstance(p,str) and p.startswith("/media/"):yield p
def pack(p,dest):
    with zipfile.ZipFile(dest,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
        z.writestr("project.json",json.dumps(p,ensure_ascii=False))
        for u in sorted(set(assets(p))):z.write(e.file(u),u[1:])
def unpack(src):
    with zipfile.ZipFile(src) as z:
        if len(z.infolist())>12000 or sum(f.file_size for f in z.infolist())>2**31:raise ValueError("项目包太大")
        p=json.loads(z.read("project.json"))
        if p.get("schema")!=1 or p.get("aspect")!="9:16":raise ValueError("不支持的项目格式或画幅")
        for k in ("name","script","cards","order","mix","defaults","history","film"):p[k]
        for s in p["order"]:
            if not re.fullmatch("S[1-9][0-9]*",s):raise ValueError("镜头编号无效")
            for n in ("","F","V","A"):p["cards"][s+n]
        for k,c in p["cards"].items():
            if not re.fullmatch(r"(?:C|L)[1-9][0-9]*|S[1-9][0-9]*[FVA]?",k):raise ValueError("资产编号无效")
            if c["kind"] not in ("char","scene","shot","frame","video","audio"):raise ValueError("未知卡片")
            for dep in st.dependencies(p,k):p["cards"][dep]
            c["job"]=""
            if c["state"]=="生成中":c["state"]="需修改"
        mapping={}
        for u in set(assets(p)):
            if not re.fullmatch(r"/media/[0-9a-f]{32}\.(png|jpg|webp|mp4|mp3|m4a|aiff|wav)",u):raise ValueError("非法素材路径")
            z.getinfo(u[1:])
        for u in set(assets(p)):
            f=e.target(u.split(".")[-1])
            with z.open(u[1:]) as a,f.open("wb") as b:shutil.copyfileobj(a,b)
            mapping[u]=e.uri(f)
        def replace(x):
            if isinstance(x,dict):return {k:replace(v) for k,v in x.items()}
            if isinstance(x,list):return [replace(v) for v in x]
            return mapping.get(x,x) if isinstance(x,str) else x
        p=replace(p);p["id"]=e.uid();st.store(p);return p
def act(b):
    a=b["act"]
    if a=="new":return st.new(b.get("name",""))
    if a=="settings":
        data=st.read(CFG) if CFG.exists() else {}
        for kind,modes in b["settings"].items():
            for mode,fields in modes.items():
                old=data.setdefault(kind,{}).setdefault(mode,{})
                old.update({k:v for k,v in fields.items() if k!="key" or v})
        st.save(CFG,data);CFG.chmod(0o600);return {}
    p=st.project(b["id"]);k=b.get("k");c=p["cards"].get(k);d=b.get("data",{})
    if a=="save":
        for f in ("name","script","defaults","mix","order"):
            if f in d:
                if f=="order" and sorted(d[f])!=sorted(p[f]):raise ValueError("镜头清单不匹配")
                if f in ("order","mix"):p["film"]="";p["preview"]=""
                p[f]=d[f]
    elif a=="edit":st.edit(p,k,d)
    elif a=="fieldreview":
        if c["kind"]!="shot" or b["field"] not in c["data"]:raise ValueError("分镜字段无效")
        c.setdefault("reviewed",{})[b["field"]]={"note":b.get("note",""),"version":c["version"],"at":e.time.time()}
        p["history"].append({"k":k,"field":b["field"],**c["reviewed"][b["field"]]})
    elif a=="review":
        state=b["state"]
        if c["state"]=="生成中":raise ValueError("请先取消任务")
        if state=="已确认" and (c["state"] not in ("待审核","已确认") or c["kind"]!="shot" and not c["uri"]):raise ValueError("请先生成当前版本")
        if state not in ("已确认","需修改"):raise ValueError("无效审核状态")
        if state=="需修改":st.down(p,k)
        c.update(state=state,note=b.get("note",""))
        p["history"].append({"k":k,"version":c["version"],"state":state,"note":c["note"],"at":e.time.time()})
        if c["kind"]=="shot" and state=="需修改":c["state"]="需修改"
    elif a=="submit":
        if k=="plan" and "script" in b:
            if not isinstance(b["script"],str) or not b["script"].strip():raise ValueError("请先输入剧本原文")
            p["script"]=b["script"]
        return st.submit(p,k,b.get("mode"),b.get("retry"),b.get("note",""))
    elif a=="cancel":
        j=st.read(st.path(st.J,b["job"]))
        if j["pid"]!=p["id"] or j["state"] not in ("生成中","排队中"):raise ValueError("任务不在运行中")
        j.update(state="已取消",error="停止本地处理；远端已提交任务可能继续执行");st.save(st.path(st.J,j["id"]),j)
        if c and c["job"]==j["id"]:c.update(job="",state="需修改")
    else:raise ValueError("未知操作")
    st.store(p);return p
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def answer(self,data,typ="application/json",code=200):
        if typ=="application/json":data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code);self.send_header("Content-Type",typ);self.send_header("Content-Length",str(len(data)));self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff");self.end_headers();self.wfile.write(data)
    def guard(self):
        base=f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host")!=base or self.headers.get("Origin") not in (None,"http://"+base):raise ValueError("请从本机工作台打开")
    def do_GET(self):
        try:
            self.guard();u=urlsplit(self.path);q=parse_qs(u.query);a=u.path
            if a in ("/","/ui.js","/style.css"):
                f=e.ROOT/"static"/({"/":"index.html"}.get(a,a.lstrip("/")));return self.answer(f.read_bytes(),mimetypes.guess_type(f)[0]+"; charset=utf-8")
            if a.startswith("/media/"):
                f=e.file(a);size=f.stat().st_size;header=self.headers.get("Range","")
                m=re.fullmatch(r"bytes=(\d+)-(\d*)",header);start,end=(int(m[1]),min(size-1,int(m[2] or size-1))) if m else (0,size-1)
                if start>end:self.send_error(416);return
                self.send_response(206 if m else 200);self.send_header("Content-Type",mimetypes.guess_type(f)[0]);self.send_header("Accept-Ranges","bytes")
                if m:self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length",str(end-start+1));self.end_headers()
                with f.open("rb") as stream:
                    stream.seek(start);remaining=end-start+1
                    while remaining:
                        chunk=stream.read(min(remaining,1024**2))
                        if not chunk:break
                        self.wfile.write(chunk);remaining-=len(chunk)
                return
            if a=="/list":
                rows=[]
                for f in st.P.glob("*.json"):
                    p=st.read(f);rows.append({"id":p["id"],"name":p["name"],"updated":p["updated"],"total":len(p["order"]),"approved":sum(v["kind"]=="video" and v["state"]=="已确认" for v in p["cards"].values()),"cover":next((v["uri"] for v in p["cards"].values() if v["kind"]=="frame" and v["uri"]),"")})
                return self.answer(sorted(rows,key=lambda r:-r["updated"]))
            if a=="/settings":
                cfg=st.read(CFG) if CFG.exists() else {}
                for modes in cfg.values():
                    for d in modes.values():d["keySet"]=bool(d.pop("key",""))
                return self.answer(cfg)
            p=st.project(q["id"][0])
            if a=="/project":return self.answer({"p":p,"jobs":st.jobs(p["id"])})
            if a=="/package":
                with tempfile.TemporaryFile() as f:
                    pack(p,f);size=f.tell();f.seek(0);self.send_response(200);self.send_header("Content-Disposition",'attachment; filename="comic-project.zip"');self.send_header("Content-Length",str(size));self.end_headers();shutil.copyfileobj(f,self.wfile);return
            raise ValueError("未知路径")
        except Exception as ex:self.answer({"error":str(ex)},code=400)
    def do_POST(self):
        try:
            self.guard();n=int(self.headers.get("Content-Length",0))
            if not 0<n<=2**31:raise ValueError("请求大小无效")
            if self.path=="/import":
                with tempfile.TemporaryFile() as f:
                    while n:
                        chunk=self.rfile.read(min(n,1024**2))
                        if not chunk:raise ValueError("上传中断")
                        f.write(chunk);n-=len(chunk)
                    result=unpack(f)
            elif self.path.startswith("/upload?"):
                ext=parse_qs(urlsplit(self.path).query)["ext"][0]
                if ext not in ("mp3","m4a","wav","aiff") or n>128*1024**2:raise ValueError("音频格式或大小不支持")
                f=e.target(ext);f.write_bytes(self.rfile.read(n));result={"uri":e.uri(f)}
            else:
                if n>4*1024**2 or self.headers.get_content_type()!="application/json":raise ValueError("需要 JSON 请求")
                b=json.loads(self.rfile.read(n))
                if b["act"]=="probe":
                    kind=b["kind"];cfg=st.config(kind,b["mode"])
                    if cfg["mode"]=="local" and kind in ("image","video","audio"):
                        paths={"image":[e.IMG/".venv/bin/h3-image-mlx",e.IMG/"models/tokenizer.json"],"video":[e.H3/"scripts/generate.py",e.H3/"models/MiniMax-H3/FL2VA/model_index.json"],"audio":[Path(shutil.which("say") or "/missing")]}[kind]
                        if not all(x.is_file() for x in paths):raise ValueError("本机运行时或权重文件缺失")
                        result={"message":"发现本机运行时；用小样验证实际生成能力。"}
                    else:
                        u=urlsplit(cfg.get("url") or "http://127.0.0.1:11434")
                        with socket.create_connection((u.hostname,u.port or (443 if u.scheme=="https" else 80)),timeout=5):pass
                        result={"message":"服务端口可达；小样将验证认证、模型与返回格式。"}
                elif b["act"]=="refine":
                    p=st.project(b["id"]);c=p["cards"][b["k"]];snap=c["version"];cfg=st.config("text",b.get("mode") or p["defaults"]["text"])
                    data=e.plan(cfg,json.dumps({"当前字段":c["data"],"修改意见":b["note"]},ensure_ascii=False),"按意见细化指定字段："+b["field"]+"。输出对象仅含该字段，保持类型。场景仅写无人环境；动作禁止对白。")
                    with st.lock:
                        p=st.project(b["id"])
                        if p["cards"][b["k"]]["version"]!=snap:raise ValueError("卡片已变更")
                        st.edit(p,b["k"],{b["field"]:data[b["field"]]});st.store(p);result=p
                else:
                    with st.lock:result=act(b)
            self.answer(result)
        except Exception as ex:self.answer({"error":str(ex)},code=400)
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--port",type=int,default=8766);args=parser.parse_args()
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler);st.recover()
    print(f"漫剧片场 http://127.0.0.1:{args.port}",flush=True);server.serve_forever()
