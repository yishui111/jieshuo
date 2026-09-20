# -*- coding: utf-8 -*-
"""IndexTTS-2 激情解说演示：情感向量控制 + 情感文本描述控制

使用说明：
1. 确保本文件位于 index-tts 项目根目录下
2. 运行前需先安装依赖并下载模型（见项目 README）
3. 双击 启动_演示.bat 或命令行运行：.venv\Scripts\python demo_jieshuo.py
"""
import os
import time

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_AUDIO_DIR = os.path.join(ROOT_DIR, "..", "演示音频", "IndexTTS-2")
if os.path.isdir(os.path.join(ROOT_DIR, "..", "演示音频")):
    OUT_DIR = SHARED_AUDIO_DIR
else:
    OUT_DIR = os.path.join(ROOT_DIR, "output")
os.makedirs(OUT_DIR, exist_ok=True)

from indextts.infer_v2 import IndexTTS2

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

# 参考音色：项目内自带（任意清晰人声 3~10 秒均可替换）
SPK = os.path.join(ROOT_DIR, "asset/zero_shot_prompt.wav")
if not os.path.exists(SPK):
    raise FileNotFoundError(
        f"参考音频不存在: {SPK}\n"
        "请将任意 3~10 秒清晰人声录音放入 asset/zero_shot_prompt.wav"
    )
print("using speaker prompt:", SPK)

t0 = time.time()
tts = IndexTTS2(
    cfg_path=os.path.join(ROOT_DIR, "checkpoints/IndexTTS-2/config.yaml"),
    model_dir=os.path.join(ROOT_DIR, "checkpoints/IndexTTS-2"),
    use_fp16=True,
    device="cuda",
    use_cuda_kernel=False,
    use_deepspeed=False,
)
print(f"model loaded in {time.time() - t0:.1f}s")

t0 = time.time()
tts.infer(
    spk_audio_prompt=SPK,
    text=FOOTBALL,
    output_path=os.path.join(OUT_DIR, "01_足球解说_情绪文本_激动.wav"),
    use_emo_text=True,
    emo_text="极度激动兴奋，热血呐喊，亢奋",
)
print(f"emo_text done in {time.time() - t0:.1f}s")

t0 = time.time()
tts.infer(
    spk_audio_prompt=SPK,
    text=GAME,
    output_path=os.path.join(OUT_DIR, "02_游戏解说_情感向量_兴奋.wav"),
    # 情感向量顺序: [喜, 怒, 哀, 惧, 厌恶, 低落, 惊喜, 平静]
    emo_vector=[0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.85, 0.0],
)
print(f"emo_vector done in {time.time() - t0:.1f}s")
print("ALL DONE")
