# 激情解说 · 端到端流水线（视频/文字 → 解说词 → 激情语音）

给它一个视频（或者不给视频，直接给一段文字），它就能产出一支**激情洋溢的解说音频**
（足球解说、游戏解说那种感觉）。整条链路是：

```
输入（视频 / 主题文字）
   │ ①视频理解：ffmpeg 抽帧 + 本地视觉模型(Ollama qwen3-vl)描述画面（给视频时才走）
   ▼
素材描述
   │ ②生成解说词：约束文档 + 素材 → DeepSeek → 结构化解说词 JSON（每段带情感标注）
   ▼
解说词（解说音频/*.json / *.md，可手改后重新合成）
   │ ③语音合成：逐段交给本地 IndexTTS-2.5，按情感标注带情绪朗读，再拼成一条音频
   ▼
解说音频（*.wav / *.mp3）
```

对应需求的五步：

| 步骤 | 实现 |
|------|------|
| 1. 寻找主要用于解说、能激情朗读的大模型 | **IndexTTS-2.5**（B站开源，当前情感表现最强的开源 TTS 之一：8 维情感向量 + 情感文字控制 + 零样本音色克隆） |
| 2. 部署模型 | `index-tts\tts_server.py` 包装成 HTTP 服务（端口 9602），本地 GPU 推理，完全离线 |
| 3. 编写约束文档 | `pipeline\约束文档.md`：严格约束解说词的输出 JSON 格式、情感词表、写作规则 |
| 4. 用 DeepSeek 生成解说词 | `pipeline\script_gen.py`：约束文档作为 system prompt + 素材发给 DeepSeek，产出并校验解说词 JSON |
| 5. 语音合成 | `pipeline\tts_client.py`：逐段带情感合成 + 拼接成片 |

没有 DeepSeek key 时，第 4 步自动回退到本地 Ollama（qwen3:14b）生成解说词，方便先跑通再配 key。

---

## 一、快速开始（3 步出音频）

```bat
:: 1. 启动解说 TTS 服务（首次启动要把模型读进显存，黑框没输出属正常，等它）
启动_解说TTS服务.bat

:: 2. （可选）把你的 DeepSeek API Key 填进 pipeline\config.yaml 的 deepseek.api_key
::    （新 clone 没有 config.yaml：先 copy pipeline\config.example.yaml pipeline\config.yaml）
::    不填也能跑，解说词由本地 Ollama 生成（效果稍弱）

:: 3. 双击一键生成，按提示输入主题文字，或直接把视频文件拖进窗口
解说_一键生成.bat
```

命令行用法：

```bat
cd pipeline
..\index-tts\.venv\Scripts\python.exe jieshuo.py --text "欧冠半决赛皇马补时逆转拜仁" --duration 60 --mp3
..\index-tts\.venv\Scripts\python.exe jieshuo.py --video "D:\比赛录像.mp4" --duration 90
..\index-tts\.venv\Scripts\python.exe jieshuo.py --text "..." --no-tts     :: 只要解说词
..\index-tts\.venv\Scripts\python.exe jieshuo.py --script "解说音频\xxx.json"  :: 改完解说词重新合成
```

产物都在根目录 `解说音频\`：`*.json`（解说词，可手改）、`*.md`（可读版）、`*.wav/.mp3`（成片）。

## 二、目录结构（本次新增部分）

```
pipeline\                      ★ 解说流水线（自己写的，全部入库）
├── 约束文档.md                 步骤3：给 DeepSeek 的输出格式约束（改风格/格式就改它）
├── script_gen.py              步骤4：DeepSeek 生成解说词（含本地 Ollama 兜底）
├── video_info.py              视频输入：ffmpeg 抽帧 + Ollama 视觉模型理解画面
├── tts_client.py              步骤5：逐段合成 + 拼接成片
├── jieshuo.py                 一键入口（交互式 / 命令行）
├── config.yaml                本机配置（DeepSeek key、音色、时长等）——不入库
├── config.example.yaml        配置模板
└── 解说音频\                  产物目录（不入库）

index-tts\                     ★ TTS 引擎目录（上游代码不入库，只入库自己写的）
├── tts_server.py              解说 TTS HTTP 服务（/health /tts /unload）
├── 启动_TTS服务.bat            启动上面的服务（端口 9602）
├── 关闭_TTS服务.bat
├── checkpoints\IndexTTS-2.5\  模型权重（约 5.2GB，ModelScope 下载）
└── asset\zero_shot_prompt.wav 解说音色参考（换成任意 3~10 秒人声即可换音色）

解说_一键生成.bat               根目录：一键解说（交互式）
启动_解说TTS服务.bat            根目录：启动 TTS 服务的快捷方式
```

## 三、配置说明（pipeline\config.yaml）

| 配置 | 说明 |
|------|------|
| `deepseek.api_key` | 你的 DeepSeek API Key（https://platform.deepseek.com 申请）；留空则用环境变量 `DEEPSEEK_API_KEY`，再没有就走本地 Ollama 兜底 |
| `deepseek.model` | 默认 `deepseek-chat` |
| `deepseek.fallback_ollama` | 本地兜底模型（默认 qwen3.5:4b，需 `ollama pull qwen3.5:4b`；显存充裕可换 qwen3:14b） |
| `tts.spk_audio` | 音色参考音频，换文件即换音色（激情男解说/女解说随你换） |
| `video.vlm_model` | 视频理解用的视觉模型，默认 `qwen3-vl:8b`，需 `ollama pull qwen3-vl:8b` |
| `output.dir` | 产物目录，默认根目录 `解说音频\`（相对 pipeline/ 写作 `../解说音频`） |

## 四、约束文档怎么改（控制解说词的样子）

`pipeline\约束文档.md` 就是发给 DeepSeek 的"格式法律"：

- **输出结构**：`{"title": ..., "segments": [{"text","emotion","intensity"},...]}`；
- **情感词表**：兴奋/喜悦/愤怒/哀伤/恐惧/厌恶/低落/惊喜/平静 九选一，`intensity` 0~1
  —— 这两项目会直接换成 IndexTTS-2.5 的 8 维情感向量（喜/怒/哀/惧/厌恶/低落/惊喜/平静）控制朗读情绪；
- **写作规则**：每段 20~40 字短句、口语化、节奏起伏、禁 markdown/emoji 等；
- 想改风格（电竞/体育/影视解说）、改段长、改 JSON 结构，直接编辑这个文档即可，代码不用动。

## 五、引擎部署（换电脑照着做）

基础环境：Windows 10/11 x64、NVIDIA 显卡（≥8GB 显存）、git、Python、ffmpeg（并加入 PATH）。
网络：git 走 `https://ghfast.top/` 代理，pip 用阿里云/清华镜像，模型走 ModelScope。

### 1. IndexTTS-2.5（解说 TTS，Python 3.11 + torch 2.8.0 cu128）

```bat
git clone https://github.com/index-tts/index-tts.git index-tts
cd index-tts
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
.venv\Scripts\pip install modelscope ninja
.venv\Scripts\python -c "from modelscope import snapshot_download; snapshot_download('IndexTeam/IndexTTS-2.5', local_dir='checkpoints/IndexTTS-2.5')"
```

参考音频放 `asset\zero_shot_prompt.wav`（任意 3~10 秒清晰人声）。
验收：`启动_TTS服务.bat` → 浏览器打开 `http://127.0.0.1:9602/health`，`"ok": true` 即就绪。

> 首次启动会自动下载 w2v-bert、BigVGAN 等辅助模型（一次性，约 2.5GB），比较耗时；
> 之后每次启动约 3~5 分钟（机械盘读权重的速度决定）。

### 2. 解说流水线（复用 index-tts 的 venv）

依赖已包含在 index-tts 的 venv 里（requests / pyyaml / numpy / soundfile），
另外需要系统装有 **ffmpeg**（视频抽帧、mp3 转码用）。视觉模型（只有给视频输入才需要）：

```bat
ollama pull qwen3-vl:8b
ollama pull qwen3.5:4b   :: 本地兜底生成解说词用（有 DeepSeek key 可不装）
```

### 3. GPT-SoVITS（可选，音色克隆备用引擎，Python 3.10 + torch 2.5.1 cu124）

```bat
git clone https://github.com/RVC-Boss/GPT-SoVITS.git GPT-SoVITS
cd GPT-SoVITS
python -m venv .venv
.venv\Scripts\pip install -r requirements_win_deploy.txt
```

依赖里的坑都整理在 `requirements_win_deploy.txt` 注释里。预训练底模（hf-mirror 下载 v2 全套）
放 `GPT_SoVITS\pretrained_models\`。验收：`启动_API.bat` → 9885。

## 六、常见问题

- **解说音频没声音 / 报 TTS 服务未就绪**：先启动 `启动_解说TTS服务.bat` 并等 `/health` 返回 `"ok":true`。
- **CUDA out of memory**：16GB 显存同一时间只跑一个引擎；另外视频理解（Ollama 视觉模型）
  和 TTS 都要显存，流水线会在视觉阶段结束后自动卸载模型再合成，但别同时开着其他大模型服务。
- **首次合成慢 / 首次启动慢**：模型从盘读进显存 + CUDA 预热，属正常；机械盘上更明显。
- **解说词不满意**：直接改 `解说音频\*.json` 后 `--script` 重新合成，不用重新生成；
  或改 `pipeline\约束文档.md` 调整文风后重新生成。
- **想换音色**：替换 `index-tts\asset\zero_shot_prompt.wav` 为任意 3~10 秒清晰人声即可（零样本克隆）。
- **演示音频**：`演示音频\` 是历史演示脚本的产物，不入库；本流水线产物在根目录 `解说音频\`。
