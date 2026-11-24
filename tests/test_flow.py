import io,json,os,subprocess,tempfile,time,unittest,zipfile
from unittest.mock import patch
tmp=tempfile.TemporaryDirectory();os.environ["STUDIO_DATA"]=tmp.name
import engine as e,studio as s,app
STORY={"characters":[{"name":"阿青","look":"短发","outfit":"白衬衣"}],"scenes":[{"location":"车站","time":"黄昏","environment":"空月台"}],"shots":[{"location":"车站","time":"黄昏","characters":["阿青"],"action":"抬头看时钟","seconds":1,"dialogue":[{"speaker":"阿青","text":"来了"}]}]}
def wait(job):
    for _ in range(1000):
        j=s.read(s.path(s.J,job["id"]))
        if j["state"] not in ("生成中","排队中"):return j
        time.sleep(.02)
    raise AssertionError("timeout")
SHEET="""| 镜号 | 地点 | 时段 | 环境 | 出镜角色 | 画面动作 | 对白 | 秒数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 车站 | 傍晚 | 空月台 | 阿青 | 抬头看时钟 | 阿青：来了 | 1 |
| 角色名 | 外貌 | 服装 |
| 阿青 | 短发 | 白衬衣 |"""

class Workflow(unittest.TestCase):
    def setUp(self):
        self.p=s.new("测试");self.id=self.p["id"];self.p["cards"],self.p["order"]=s.build(STORY);s.store(self.p)
    def api(self,act,**kw):
        with s.lock:return app.act({"act":act,"id":self.id,**kw})
    def test_local_qwen_without_xgrammar(self):
        def chat(url, body):
            self.assertNotIn("format",body)
            self.assertIn("JSON",body["messages"][0]["content"])
            return {"message":{"content":'{"ready":true}'}}
        with patch.object(e,"req",chat):
            self.assertEqual(e.plan({"mode":"local"},"测试","输出 ready"),{"ready":True})
        with patch.object(e,"req",return_value={"message":{"content":"好的"}}):
            with self.assertRaisesRegex(ValueError,"合法 JSON"):e.plan({"mode":"local"},"测试","输出 ready")

    def test_original_script_to_linked_cards_without_model_json(self):
        script="女孩说：“只住一晚。”\n橘猫伸出爪子。"
        sheet="镜号｜地点｜时段｜环境｜出镜角色｜画面动作｜对白｜秒数\n1｜楼下｜傍晚｜微光｜女孩、橘猫｜女孩蹲下，橘猫伸爪｜女孩：只住一晚。｜5秒"
        def chat(url,body):
            self.assertEqual(body["messages"][1],{"role":"user","content":script})
            self.assertNotIn("format",body)
            return {"message":{"content":sheet},"done_reason":"stop"}
        with patch.object(e,"req",chat):
            cards,order=s.plan_story({"mode":"local"},script,15,self.fail)
        self.assertEqual(order,["S1"])
        d=cards["S1"]["data"]
        self.assertEqual([cards[k]["data"]["name"] for k in d["cast"]],["女孩","橘猫"])
        self.assertEqual(cards[d["scene"]]["data"]["time"],"黄昏")
        self.assertEqual(d["dialogue"],"女孩：只住一晚。")
        self.assertNotIn("只住一晚",d["action"])
    def test_sheet_errors_do_not_save_partial_plan(self):
        seen=[];bad=SHEET.replace("阿青：来了","没有说话人")
        with patch.object(e,"local_shot_text",side_effect=[bad,SHEET]) as call:
            cards,order=s.plan_story({"mode":"local"},"原文",15,lambda:seen.append(1))
            self.assertEqual(call.call_args.args[1],"原文")
            self.assertEqual(cards["C1"]["data"]["outfit"],"白衬衣")
            self.assertEqual(order,["S1"])
        self.assertEqual(seen,[1])
        with patch.object(e,"local_shot_text",return_value=bad) as call:
            with self.assertRaisesRegex(ValueError,"缺少说话人"):s.plan_story({"mode":"local"},"原文",15,lambda:None)
            self.assertEqual(call.call_count,2)
        with patch.object(e,"req",return_value={"done_reason":"length","message":{"content":SHEET}}):
            with self.assertRaisesRegex(ValueError,"长度上限"):s.plan_story({"mode":"local"},"原文",15,self.fail)
    def test_api_still_uses_json(self):
        with patch.object(e,"plan",return_value=STORY) as call:
            self.assertEqual(s.plan_story({"mode":"api"},"原文",15,self.fail)[1],["S1"])
            self.assertEqual(call.call_args.args[1],"原文")
    def test_scene_time_matching(self):
        import copy
        data=copy.deepcopy(STORY)
        data["scenes"][0]["time"]=" 傍晚 "
        data["shots"][0]["location"]=" 车站"
        cards,order=s.build(data)
        self.assertEqual(cards[cards["S1"]["data"]["scene"]]["data"]["time"],"黄昏")
        data["shots"][0]["time"]="不详"
        with self.assertRaisesRegex(ValueError,"镜头 1.*不详"):s.build(data)

    def test_reference_gate_and_edits(self):
        with self.assertRaisesRegex(ValueError,"先确认"):self.api("submit",k="S1F")
        c=self.p["cards"]
        for v in c.values():v["state"]="已确认"
        s.edit(self.p,"S1",{"dialogue":"旁白：到了"});self.assertEqual(c["S1V"]["state"],"已确认");self.assertEqual(c["S1A"]["state"],"上游已更新")
        s.edit(self.p,"C1",{"look":"长发"});self.assertEqual(c["S1F"]["state"],"上游已更新");self.assertEqual(c["S1V"]["state"],"上游已更新")
    def test_package_rejects_missing(self):
        self.p["cards"]["C1"]["uri"]="/media/"+e.uid()+".png";z=io.BytesIO()
        with zipfile.ZipFile(z,"w") as f:f.writestr("project.json",json.dumps(self.p))
        with self.assertRaises(KeyError):app.unpack(z)
    def test_resume_queries_without_submit(self):
        calls=[];pic=e.target("png");pic.write_bytes(b'\x89PNG'+bytes(30))
        def request(url,*a,**kw):
            calls.append(url);return {"status":"completed","b64_json":e.base64.b64encode(pic.read_bytes()).decode()}
        def ticket(*a):return "existing"
        ticket.id="request"
        with patch.object(e,"req",request):e.generate("image",{"mode":"api","model":"m","url":"https://fake/submit","query":"https://fake/{id}"},"",[],0,"",ticket,lambda:None)
        self.assertEqual(calls,["https://fake/existing"])
    def test_render_and_roundtrip(self):
        import shutil
        if not shutil.which(e.FF):self.skipTest("requires FFmpeg")
        png=e.target("png");vid=e.target("mp4");wav=e.target("wav")
        e.run([e.FF,"-y","-f","lavfi","-i","color=c=navy:s=144x256","-frames:v",1,png])
        e.run([e.FF,"-y","-loop",1,"-i",png,"-t",1,"-pix_fmt","yuv420p",vid])
        e.run([e.FF,"-y","-f","lavfi","-i","sine=frequency=410","-t",.8,wav]);calls=[]
        def generate(kind,cfg,prompt,refs,*rest):
            calls.append((kind,prompt,refs));return e.uri({"audio":wav,"video":vid,"image":png}[kind])
        with patch.object(e,"generate",generate),patch.object(e,"local_shot_text",return_value=SHEET):
            self.assertEqual(wait(self.api("submit",k="plan",script="阿青等车。"))["state"],"完成")
            for k in ("S1","C1","L1","S1F","S1V","S1A"):
                if k!="S1":
                    j=wait(self.api("submit",k=k));self.assertEqual(j["state"],"完成",j)
                self.api("review",k=k,state="已确认")
            self.assertEqual(calls[2][2],[e.uri(png)]*2);self.assertNotIn("来了",calls[2][1]);self.assertEqual(calls[3][2],[e.uri(png)])
            self.api("edit",k="S1V",data={"start":.1,"end":.9,"sfx":e.uri(wav)})
            self.api("save",data={"mix":{"bgm":e.uri(wav),"subs":True}})
            j=wait(self.api("submit",k="film"));self.assertEqual(j["state"],"完成",j)
        info=subprocess.run([e.FF,"-i",e.file(j["uri"])],capture_output=True).stderr.decode()
        self.assertIn("720x1280",info);self.assertIn("Audio: aac",info)
        z=io.BytesIO();app.pack(s.project(self.id),z);self.assertNotIn("connections.json",zipfile.ZipFile(z).namelist())
        other=app.unpack(z);self.assertNotEqual(other["id"],self.id);self.assertEqual(e.file(other["film"]).read_bytes(),e.file(j["uri"]).read_bytes())
