import time, sys
T0 = time.perf_counter(); last = T0
def mark(label):
    global last
    now = time.perf_counter()
    print(f"[{now-T0:8.2f}s] (+{now-last:7.2f}s) {label}", flush=True)
    last = now

mark("解释器启动完毕")
import pandas;       mark("import pandas")
import torch;        mark("import torch")
import transformers; mark("import transformers")
import gradio;       mark("import gradio")
mark("=== 基础依赖 import 完成 ===")

sys.path.insert(0, ".")
sys.path.insert(0, "indextts")
try:
    from indextts.infer_v2 import IndexTTS2
    mark("import IndexTTS2 (infer_v2)")
except Exception as e:
    mark(f"import IndexTTS2 失败: {e}")

import os
os.makedirs("checkpoints", exist_ok=True)
if os.path.exists("checkpoints/IndexTTS-2/config.yaml"):
    tts = IndexTTS2(
        model_dir="checkpoints/IndexTTS-2",
        cfg_path="checkpoints/IndexTTS-2/config.yaml",
        use_fp16=True,
        use_qwen_emo=False,
    )
    mark("IndexTTS2 模型加载完成（核心耗时）")
else:
    mark("config.yaml 不存在，跳过模型加载")

print(f"\n>>> 总计 {time.perf_counter()-T0:.2f}s", flush=True)
