# 映格 · 9:16 漫剧片场

面向单人创作者的本地工作台。从原文拆镜、角色三视图和纯环境参考图，到逐镜关键帧、视频、配音、字幕与 720×1280 MP4。浏览器无需 npm 或前端构建。模型和权重不随仓库分发。

## 启动
需要 Python 3.10+。已有本地运行环境的 Mac 可在项目目录执行：

```sh
zsh start.command
```

跨平台启动：运行 `python3 app.py`，访问 http://127.0.0.1:8766 。可用 `--port 8767` 更换端口。服务只绑定本机，供一个用户使用；请从 127.0.0.1 地址打开。FFmpeg 要有 libx264、AAC、libass 字幕滤镜和可显示中文的字体。通过 PATH 或 FFMPEG 环境变量指定，也会尝试相邻 H3 虚拟环境中的 FFmpeg。

## 第一次制作
1. 右上角 **连接设置**：文本、图片、视频、配音各选本地或 HTTP API。保存后先测试，再按需生成小样（可能产生费用）。连接测试检查端口或本地文件；小样才实际调用模型。图像小样传入参考图，视频小样传入首帧。小样在任务记录页显示。服务不报告自身能力时，不自动推断它支持全部参考图、尺寸或时长。
2. 输入故事，拆分剧本。蓝色为动作，紫色为角色，绿色为环境，黄色为对白。检查并确认每张镜头卡。建议先用 2–3 镜短故事调通。重新拆镜会归档原卡片。
3. 编辑每个角色的外貌、服装、固定音色，生成并确认三视图。每个地点与时段共享一张场景参考图，结构化地保存地点、时间和环境，生图只取环境字段。修改建议可用于重做图片，也可指定字段让文本模型细化。
4. 每镜关键帧实际传入本镜所有角色图和场景图，确认后制作视频。画面提示词使用视觉动作，不拼接独立对白。只重做视频会保留关键帧。不保证生成模型始终遵守一致性或无文字要求，需人工复核。
5. 声音与剪辑：对白按“角色：台词”分行，逐行合成并拼接，未指定角色使用默认音色；可试听、重做和确认。无对白可跳过。设定镜头顺序和裁剪区间，上传 BGM、单镜音效并调节三轨音量。可预览单镜字幕与配音；以导出的成片检查最终混音。字幕按镜头内各行等分计时，非强制对齐。超出裁剪范围的声音会截短；不保留视频模型生成的原声音轨。
6. 所有分镜与视频确认后，点击 **合成最终 MP4**。未确认的已生成配音也会阻止导出。

## 连接协议
**本地拆镜：** 点击时提交输入框原文，Qwen 阅读故事并返回逐镜表。Python 提取出镜角色、场景与时段、画面动作、对白和时长，验证后一次写入待审核卡片；无需模型输出嵌套 JSON。

**本地文本：** Ollama 的 /api/chat，默认 qwen3.5:4b，可修改模型与完整地址。先用 Ollama 安装并启动所选模型。Mac 若已有相邻 ollama-runtime/models，启动脚本会尝试复用。API 文本使用 OpenAI 风格 Chat Completions，要求支持 JSON 对象输出。

**本地 H3 是命令行推理，不是云端 API。** 默认复用仓库旁的 h3-runtime（视频）和 h3-image-runtime（图片），分别由 H3_RUNTIME / H3_IMAGE_RUNTIME 覆盖。视频对接 [minimax-h3-mac](https://github.com/Argus-AiTeam/minimax-h3-mac) 的 scripts/generate.py；适配的上游提交为 3fcc9f8c557cf353400b1acf737b985e524a509f。需先按上游说明准备 .venv、MiniMax-H3 FL2VA 与 Turbo LoRA，再执行 zsh scripts/apply_h3_i2v_patch.zsh 检查/应用首帧补丁。图片使用 h3-image-mlx，安装脚本 scripts/setup_h3_image.zsh 以现有视频环境的 Python 创建独立环境，并在确认许可后下载权重。三视图 1536×1024；场景和关键帧 576×1024；本地低内存视频 288×512。运行时、权重、Metal 和可用内存决定本机能否推理。仅需远程 API 时无需安装 H3。

**自定义生成网关：** 填完整 endpoint，可选 Bearer 密钥。不同厂商若不符合下表，应在本地加一层协议转换；并非仅填模型名就支持所有厂商。
| 类型 | 请求 | 响应 |
|---|---|---|
| 文本 | model, messages, response_format | choices[0].message.content 中的 JSON |
| 图片 | model, prompt, n=1, width, height, reference_images（按顺序传 data URL） | data[0].url 或 data[0].b64_json |
| 视频 | model, prompt, duration, aspect_ratio, first_frame_image（data URL） | url / video_url 或 task_id |
| 音频 | OpenAI 风格 model, input, voice, response_format=mp3 | MP3 二进制 |
| 异步任务查询 | GET 已配置地址，将 {id} 替换为已保存任务号 | status=succeeded/completed 与结果地址，或 failed 与 error |

本地配音调用 macOS say（可用 say -v '?' 查看系统音色）；其他系统可用音频 API。远程接口须支持所选音色、约定的尺寸、参考图和时长。生成时可临时覆盖项目默认服务。

## 存档、队列与边界
- 每张资产和镜头都有状态、版本与反馈。角色/环境修改会沿引用关系标记关键帧和视频；只改对白时保留已确认画面，更新配音。拒绝、重新生成和确认由本地工作流检查。
- 编辑字段在离开输入框时自动保存。**保存项目** 下载 ZIP，包含当前及历史引用的素材、审核、已保存的生成参数；**导入项目** 校验格式、素材和引用，另建项目，不覆盖原项目。密钥不进入 ZIP；数据、日志、配置和权重均不提交到 Git。
- 本机单 worker 串行执行以控制内存。刷新浏览器不会停止任务；重启后恢复排队工作与已取得任务号的远程查询。无法判断上次远端是否接单时，普通重试拦截，需先在供应商处核对。远端支持 Idempotency-Key 时可使用任务 ID 去重。取消会阻止结果写回并终止运行中的本地媒体进程，不保证第三方撤销计费。
- 服务测试与使用真实模型生成是两件事。自动化测试使用替代生成器检查输入绑定与审核状态，真实 FFmpeg 进行编码与混音。未以这些测试证明人脸一致性、成片美观或供应商可用性。
- 文件分工：app.py 本地 HTTP/项目包；studio.py 队列、依赖、版本及状态；engine.py 模型适配和媒体合成；static/ 浏览器工作台。默认 data/ 保存本机项目；可用 STUDIO_DATA 更换路径。

## 验证
```sh
python3 -m unittest discover -s tests -v
```
测试在临时目录工作，不需 API Key。导出测试需 FFmpeg。架构参考：[Toonflow](https://github.com/HBAI-Ltd/Toonflow-app)、[ComicAgent](https://github.com/robiteame/easy_comic_agent)、[ai-manju](https://github.com/acdpy/ai-manju)、[drama-skills](https://github.com/zenstory-ai/drama-skills)。
