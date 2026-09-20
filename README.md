# 激情解说 TTS：CosyVoice 2 / IndexTTS-2 / GPT-SoVITS

需求很简单：给我一段解说词，用激情洋溢的声音解说出来（足球解说、游戏解说那种感觉），
只要有文字就能解说。为此我选了三个 LLM 架构的语音合成大模型，全部本地部署、GPU 推理、
完全离线、没有任何 API 收费：

| # | 目录 | 引擎 | 出品方 | 强项 | 端口 |
|---|------|------|--------|------|------|
| 1 | `CosyVoice/` | CosyVoice 2（0.5B） | 阿里 FunAudioLLM | 自然语言指令控语气："用极其兴奋、激动、呐喊的语气解说" | 9600 |
| 2 | `index-tts/` | IndexTTS-2 | 哔哩哔哩 | 情感向量（喜/怒/哀/惧…8 维）+ 情感文字描述 | 9601 |
| 3 | `GPT-SoVITS/` | GPT-SoVITS v2 | RVC-Boss | 参考音频音色克隆：给一段录音就能用 TA 的音色解说 | 9872 / API 9885 |

**这个仓库只提交我自己写的部分**——每个引擎目录里的 `demo_jieshuo.py`（激情解说演示脚本）、
`启动_*.bat` / `关闭_*.bat` 启动脚本，以及根目录的文档。引擎源码、`.venv` 虚拟环境、
模型权重（合计 20 GB 左右）都不进仓库，换电脑时按本文档重新部署一遍即可。

日常使用方法（三个引擎怎么控语气、怎么换音色）看 [使用说明.md](使用说明.md)，
本文只讲怎么从零装起来。

本机环境：Windows 10 / RTX 4080 16GB；显存 16GB 同一时间只跑一个引擎，跑第二个前先关窗口。

---

## 一、仓库里有什么

```
CosyVoice/
├── demo_jieshuo.py        激情解说演示（instruct2 模式：一句话指令控语气）
├── 启动_WebUI.bat          WebUI → http://127.0.0.1:9600
├── 启动_演示.bat           跑 demo_jieshuo.py，音频出在 演示音频\CosyVoice2\
└── 关闭_WebUI.bat          按端口停进程

index-tts/
├── demo_jieshuo.py        激情解说演示（emo_text 情感文字 / emo_vector 8 维情感向量）
├── 启动_WebUI.bat          WebUI → http://127.0.0.1:9601
├── 启动_演示.bat
├── 关闭_WebUI.bat
├── _diag_disk.py          诊断：模型权重的磁盘读取速度
└── _diag_startup.py       诊断：启动卡在哪一步

GPT-SoVITS/
├── demo_jieshuo.py        激情解说演示（走本机 API 音色克隆）
├── 启动_WebUI.bat          推理 WebUI → http://127.0.0.1:9872
├── 启动_API.bat            HTTP API → http://127.0.0.1:9885（演示脚本依赖它）
├── 启动_演示.bat / 关闭服务.bat
├── _run_test.bat          部署自测
└── requirements_win_deploy.txt    我整理的 Windows 部署依赖清单（含编译处理说明）
```

引擎本体、`.venv/`、`pretrained_models/`、`checkpoints/`、参考音频 `asset/`、
生成的 `演示音频/` 都不入库。

---

## 二、从零部署（换电脑照着做）

### 0. 基础环境与网络

- Windows 10/11 x64 + NVIDIA 显卡（建议 8GB 显存以上）
- git、Python（下面每个引擎用自己的小版本，见各节）
- 网络准备：GitHub 走 `https://ghfast.top/` 前缀代理；pip 用阿里云/清华镜像；
  模型下载——CosyVoice2、IndexTTS-2 走 **ModelScope**，GPT-SoVITS 走 **hf-mirror.com**。
- Windows 上**不需要 conda**：文本正则化我已改用纯 Python 的 `wetext`（不是 WeTextProcessing）。

### 1. CosyVoice 2（Python 3.10 + torch 2.3.1 cu121）

```bat
git clone https://github.com/FunAudioLLM/CosyVoice.git CosyVoice
cd CosyVoice
git clone https://github.com/FunAudioLLM/Matcha-TTS.git third_party/Matcha-TTS
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

模型（约 4.6 GB，ModelScope 官方仓库 `iic/CosyVoice2-0.5B`）下载到
`pretrained_models\CosyVoice2-0.5B\`。
参考音频放 `asset\zero_shot_prompt.wav`（任意 3~10 秒清晰人声）。

验收：`启动_WebUI.bat` → 9600 出页面；`启动_演示.bat` 出第一支解说音频。

### 2. IndexTTS-2（Python 3.11 + torch 2.8.0 cu128）

```bat
git clone https://github.com/index-tts/index-tts.git index-tts
cd index-tts
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

模型（约 12 GB）从 ModelScope / hf-mirror 下载 `IndexTTS-2` 全套到
`checkpoints\IndexTTS-2\`；参考音频同上放 `asset\`。

验收：`启动_WebUI.bat` → 9601；`启动_演示.bat`。
启动异常时先跑 `_diag_startup.py`、`_diag_disk.py` 看卡点和磁盘读取速度。

### 3. GPT-SoVITS（Python 3.10 + torch 2.5.1 cu124）

```bat
git clone https://github.com/RVC-Boss/GPT-SoVITS.git GPT-SoVITS
cd GPT-SoVITS
python -m venv .venv
.venv\Scripts\pip install -r requirements_win_deploy.txt
```

依赖里的坑都整理在 `requirements_win_deploy.txt` 注释里：`opencc` 用官方 wheel
（不要 `--no-binary`）；`openai-whisper`、`pyopenjtalk` 两个老包要本地构建
（setuptools<81 + cmake，照注释走）。

预训练底模（约 1.1 GB，hf-mirror 下载 GPT-SoVITS v2 全套）放
`GPT_SoVITS\pretrained_models\`。

验收：`启动_API.bat` → 9885；再 `启动_演示.bat`（演示走 API 音色克隆）。

---

## 三、常见问题

- **CUDA out of memory**：16GB 显存同时只能跑一个引擎，关掉另一个的窗口再启动。
- **首次启动慢（1~4 分钟）**：模型从机械盘读进显存，属正常；首次合成还有 CUDA 预热。
- **换音色**：把 `demo_jieshuo.py` / WebUI 里的参考音频换成任意 3~10 秒清晰人声即可
  （IndexTTS-2 / GPT-SoVITS 都是零样本克隆）。
- **演示音频**：`演示音频\` 是运行 `demo_jieshuo.py` 的产物，仓库里没有，
  想听就自己跑一遍演示脚本生成。
