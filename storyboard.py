"""Turn a director's shot sheet into a linked plan; JSON syntax is never model-authored."""
import math
import re

INSTRUCTION = """你是竖屏漫剧导演。user 消息就是待改编的剧本原文。读完整篇，保留起因、转折、结局和原文对白，通常分成 6–8 镜，短故事可以更少。输出中文表格，不要 JSON，不要解释。
每镜一行，用 | 分列，单元格内不换行，不用 |。表头必须是：
镜号 | 地点 | 时段 | 环境 | 出镜角色 | 画面动作 | 对白 | 秒数
镜号从1递增；同一地点、角色名称保持一致；时段限定白天、黄昏、夜晚。环境仅写无人地点与光线。角色用顿号分隔，包括动物角色，无角色写“无”。画面动作包含可见动作和景别，不写台词。对白写“角色：原话”，多句用“；角色：原话”连接，无对白写“无”。秒数写正整数。不要输出示例或省略行。分镜表后另列一张角色设定表，三列为「角色名 | 外貌 | 服装」，每个角色一行，动物没有服装写无。"""

EMPTY={'','无','无对白','无台词','无角色','无人物','无出镜角色','空镜','空镜头','—','-','/','无对话','（无）'}
def cells(line):
    return [v.strip().strip('*').strip() for v in line.strip().replace('｜','|').strip('|').split('|')]

def parse(text,cap,scene_key):
    characters={};scenes={};shots=[];profiles={}
    for lineno,line in enumerate(text.splitlines(),1):
        if not line.strip() or line.strip().startswith('```'):continue
        row=cells(line)
        if len(row)==1:
            if re.match(r'^\s*(?:镜头|分镜)?\s*\d',line):raise ValueError(f"第 {lineno} 行没有按列拆分")
            continue
        if ('地点' in row and any('对白' in x for x in row)) or all(re.fullmatch(r'[:\s\-]+',x) for x in row):continue
        if len(row)==3 and row[0] in ("角色名","角色","姓名") and row[2] in ("服装","衣着"):continue
        if len(row)==3 and shots and not re.search(r'\d',row[0]) and row[0] in characters:
            profiles[row[0]]=dict(name=row[0],look=row[1],outfit=row[2]);continue
        if len(row)!=8:raise ValueError(f"第 {lineno} 行有 {len(row)} 列，需要 8 列")
        number,location,t,environment,cast,action,dialogue,duration=row
        idx=re.fullmatch(r'(?:第|分镜|镜头|镜号|S)?\s*0*(\d+)\s*(?:镜|号|[.、])?',number,re.I)
        if not idx or int(idx[1])!=len(shots)+1:raise ValueError(f"第 {lineno} 行镜号应为 {len(shots)+1}")
        key=scene_key({'location':location,'time':t},f"镜头 {number}")
        if not action or action in EMPTY or not environment:raise ValueError(f"镜头 {number} 缺少动作或环境")
        scenes.setdefault(key,dict(location=key[0],time=key[1],environment=environment))
        names=[] if cast in EMPTY else list(dict.fromkeys(v.strip() for v in re.split(r'[、,，;；]',cast) if v.strip()))
        for n in names:characters.setdefault(n,dict(name=n,look='',outfit=''))
        lines=[]
        if dialogue not in EMPTY:
            for part in re.split(r'[;；]\s*(?=[^：:;；]{1,20}[:：])',dialogue):
                match=re.fullmatch(r'\s*([^：:]{1,40})[:：]\s*(.+)',part)
                if not match:raise ValueError(f"镜头 {number} 的对白缺少说话人")
                speaker,words=(x.strip() for x in match.groups())
                if len(words)>1 and (words[0],words[-1]) in [('“','”'),('「','」'),('"','"')]:words=words[1:-1]
                if not words.strip():raise ValueError(f"镜头 {number} 对白为空")
                lines.append(dict(speaker=speaker,text=words))
                action=action.replace(words,'').replace('“”','').replace('「」','').strip()
        match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:秒|s)?',duration,re.I)
        if not action or not match:raise ValueError(f"镜头 {number} 缺少独立动作或有效时长")
        seconds=float(match[1])
        if not math.isfinite(seconds) or not 1<=seconds<=cap:raise ValueError(f"镜头 {number} 时长应为 1–{cap:g} 秒")
        shots.append(dict(location=key[0],time=key[1],characters=names,action=action,dialogue=lines,seconds=seconds))
    if not shots:raise ValueError("未找到分镜表数据行")
    characters.update(profiles)
    return dict(characters=list(characters.values()), scenes=list(scenes.values()), shots=shots)
