# -*- coding: utf-8 -*-
"""GPT-SoVITS 激情解说演示：通过 api_v2.py 的 HTTP 接口合成。

使用说明：
1. 先启动 API 服务：双击 启动_API.bat（默认 9885 端口）
2. 再运行本脚本：双击 启动_演示.bat 或命令行运行 .venv\Scripts\python demo_jieshuo.py
"""
import os
import requests

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_AUDIO_DIR = os.path.join(ROOT_DIR, "..", "演示音频", "GPT-SoVITS")
if os.path.isdir(os.path.join(ROOT_DIR, "..", "演示音频")):
    OUT_DIR = SHARED_AUDIO_DIR
else:
    OUT_DIR = os.path.join(ROOT_DIR, "output")
os.makedirs(OUT_DIR, exist_ok=True)

API = "http://127.0.0.1:9885/tts"

# 参考音频：优先使用项目内 asset，否则尝试根目录 CosyVoice 的音频
REF_WAV_CANDIDATES = [
    os.path.join(ROOT_DIR, "asset", "zero_shot_prompt.wav"),
    os.path.join(ROOT_DIR, "..", "CosyVoice", "asset", "zero_shot_prompt.wav"),
]
REF_WAV = None
for c in REF_WAV_CANDIDATES:
    if os.path.exists(c):
        REF_WAV = c
        break
if REF_WAV is None:
    raise FileNotFoundError(
        "未找到参考音频。请将任意 3~10 秒清晰人声放入 asset/zero_shot_prompt.wav"
    )
PROMPT_TEXT = "希望你以后能够做的比我还好呦。"

FOOTBALL = (
    "漂亮！球进了！这是一记世界波！禁区外拔脚怒射，皮球像出膛的炮弹一样直挂死角，"
    "守门员甚至来不及做出反应！全场沸腾了！八万名球迷的呐喊声震耳欲聋！"
    "这就是足球的魅力，这就是绿茵场上的激情时刻！"
)
GAME = (
    "注意看，中路团战一触即发！打野绕后完美切入，中单跟上输出，一套技能瞬秒对面双C！"
    "漂亮！这波操作直接拉满！对面完全没有反应过来！推塔！拿龙！一波带走！比赛结束！"
    "恭喜他们，拿下了这场关键的胜利！"
)

for name, text in [
    ("01_足球解说_参考音色激情.wav", FOOTBALL),
    ("02_游戏解说_参考音色激情.wav", GAME),
]:
    payload = {
        "text": text,
        "text_lang": "zh",
        "ref_audio_path": REF_WAV,
        "prompt_text": PROMPT_TEXT,
        "prompt_lang": "zh",
        "speed_factor": 1.05,
    }
    r = requests.post(API, json=payload, timeout=300)
    r.raise_for_status()
    path = os.path.join(OUT_DIR, name)
    with open(path, "wb") as f:
        f.write(r.content)
    print("saved", path, f"({len(r.content) / 1024:.0f} KB)")
print("ALL DONE")
