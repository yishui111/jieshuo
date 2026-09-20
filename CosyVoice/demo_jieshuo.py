# -*- coding: utf-8 -*-
"""CosyVoice2 激情解说演示：instruct2 模式（自然语言指令控制语气）+ zero_shot 模式

使用说明：
1. 确保本文件位于 CosyVoice 项目根目录下
2. 运行前需先安装依赖并下载模型（见项目 README）
3. 双击 启动_演示.bat 或命令行运行：.venv\Scripts\python demo_jieshuo.py
"""
import os
import sys
import time

# 兼容：项目单独复制走时，输出到项目内 output/；在根目录结构下输出到 ../演示音频/
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_AUDIO_DIR = os.path.join(ROOT_DIR, "..", "演示音频", "CosyVoice2")
if os.path.isdir(os.path.join(ROOT_DIR, "..", "演示音频")):
    OUT_DIR = SHARED_AUDIO_DIR
else:
    OUT_DIR = os.path.join(ROOT_DIR, "output")
os.makedirs(OUT_DIR, exist_ok=True)

sys.path.append(os.path.join(ROOT_DIR, "third_party/Matcha-TTS"))
from cosyvoice.cli.cosyvoice import CosyVoice2
from cosyvoice.utils.file_utils import load_wav
import torchaudio

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

t0 = time.time()
model = CosyVoice2(
    os.path.join(ROOT_DIR, "pretrained_models/CosyVoice2-0.5B"),
    load_jit=False, load_trt=False, fp16=False
)
print(f"model loaded in {time.time() - t0:.1f}s, sample_rate={model.sample_rate}")

PROMPT_WAV = os.path.join(ROOT_DIR, "asset/zero_shot_prompt.wav")
if not os.path.exists(PROMPT_WAV):
    raise FileNotFoundError(
        f"参考音频不存在: {PROMPT_WAV}\n"
        "请将任意 3~10 秒清晰人声录音放入 asset/zero_shot_prompt.wav"
    )


def synth(name, text, mode, **kwargs):
    t0 = time.time()
    chunks = []
    if mode == "instruct2":
        gen = model.inference_instruct2(text, kwargs["instruct_text"], PROMPT_WAV)
    else:
        gen = model.inference_zero_shot(text, "希望你以后能够做的比我还好呦。", PROMPT_WAV)
    for out in gen:
        chunks.append(out["tts_speech"])
    import torch
    speech = torch.cat(chunks, dim=1)
    path = os.path.join(OUT_DIR, name)
    torchaudio.save(path, speech, model.sample_rate)
    print(f"saved {path} ({speech.shape[1] / model.sample_rate:.1f}s, synth {time.time() - t0:.1f}s)")


synth("01_足球解说_instruct2_激动呐喊.wav", FOOTBALL, "instruct2",
      instruct_text="你是一位无比激情的足球解说员，请用极其兴奋、激动、呐喊的语气解说")
synth("02_游戏解说_instruct2_激情亢奋.wav", GAME, "instruct2",
      instruct_text="你是一位亢奋的电竞解说员，请用激情澎湃、语速飞快、热血沸腾的语气解说")
synth("03_足球解说_zero_shot.wav", FOOTBALL, "zero_shot")
print("ALL DONE")
