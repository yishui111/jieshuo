# -*- coding: utf-8 -*-
"""解说 TTS HTTP 服务：把 IndexTTS-2 / 2.5 包装成稳定的 REST 接口，供解说流水线调用。

用法（在 index-tts 目录下）：
    .venv\\Scripts\\python.exe tts_server.py --version 2.5 --model_dir checkpoints/IndexTTS-2.5 --port 9602

接口：
    GET  /health  -> {"ok": true, "model_dir": ..., "version": ..., "device": ...}
    POST /tts     -> 请求体见 TTSRequest；合成 wav 落盘后返回 {"file": ..., "seconds": ...}
    POST /unload  -> 释放显存（把模型移出 GPU，进程保留）

情感控制（三选一，优先级从高到低）：
    emo_vector : 8 维向量 [喜, 怒, 哀, 惧, 厌恶, 低落, 惊喜, 平静]，各 0~1
    emotion    : 情感标签 + intensity 强度（见 EMOTION_VECTORS），由服务端换算成向量
    emo_text   : 情感文字描述（需启动时带 --qwen_emo 加载 QwenEmotion 模型）
"""

import argparse
import os
import sys
import time
import threading

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

OUT_DIR = os.path.join(ROOT_DIR, "outputs", "tts_server")

# 8 维情感向量顺序: [喜, 怒, 哀, 惧, 厌恶, 低落, 惊喜, 平静]
EMOTION_VECTORS = {
    "兴奋": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.0],
    "喜悦": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "愤怒": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.0],
    "哀伤": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "恐惧": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
    "厌恶": [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
    "低落": [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
    "惊喜": [0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
    "平静": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.8],
}


def parse_args():
    p = argparse.ArgumentParser(description="解说 TTS HTTP 服务")
    p.add_argument("--version", default="2.5", choices=["2", "2.5"], help="模型版本")
    p.add_argument("--model_dir", default=os.path.join("checkpoints", "IndexTTS-2.5"))
    p.add_argument("--port", type=int, default=9602)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--qwen_emo", action="store_true", default=False,
                   help="加载 QwenEmotion（仅 emo_text 情感文字模式需要；默认关闭以省约1GB内存/显存，流水线用情感向量模式无需加载）")
    p.add_argument("--no_qwen_emo", dest="qwen_emo", action="store_false")
    return p.parse_args()


ARGS = parse_args()


def build_tts():
    """按版本加载模型；显存 >=10GB 用 bf16，否则 fp16。"""
    import torch
    if ARGS.version == "2.5":
        from indextts.infer_v2_5 import IndexTTS2
    else:
        from indextts.infer_v2 import IndexTTS2

    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3) if torch.cuda.is_available() else 0
    kwargs = dict(cfg_path=os.path.join(ARGS.model_dir, "config.yaml"), model_dir=ARGS.model_dir)
    if vram_gb >= 10:
        kwargs["use_bf16"] = True
    else:
        kwargs["use_fp16"] = True
    if ARGS.qwen_emo:
        kwargs["use_qwen_emo"] = True
    print(f">> 加载模型: version={ARGS.version} dir={ARGS.model_dir} vram={vram_gb:.1f}GB kwargs={kwargs}")
    t0 = time.time()
    tts = IndexTTS2(**kwargs)
    print(f">> 模型加载完成，耗时 {time.time() - t0:.0f}s")
    return tts


TTS = None
TTS_LOCK = threading.Lock()


def emotion_to_vector(emotion: str, intensity: float):
    if not emotion:
        return None
    base = EMOTION_VECTORS.get(emotion)
    if base is None:
        raise ValueError(f"未知情感标签: {emotion}，可选: {list(EMOTION_VECTORS)}")
    intensity = max(0.0, min(1.0, float(intensity)))
    return [round(v * intensity, 3) for v in base]


def create_app():
    from fastapi import FastAPI
    from pydantic import BaseModel, Field
    from typing import List, Optional

    app = FastAPI(title="解说 TTS 服务", version=ARGS.version)

    class TTSRequest(BaseModel):
        text: str = Field(..., description="要合成的解说词")
        emo_vector: Optional[List[float]] = Field(None, description="8维情感向量")
        emotion: Optional[str] = Field(None, description="情感标签，如 兴奋")
        intensity: float = Field(0.9, description="情感强度 0~1")
        emo_text: Optional[str] = Field(None, description="情感文字描述（需 --qwen_emo）")
        use_emo_text: bool = Field(False, description="启用情感文字控制")
        spk_audio: str = Field("asset/zero_shot_prompt.wav", description="音色参考音频（相对 index-tts 目录）")
        lang: str = Field("zh_CN")
        duration_factor: float = Field(1.0, description="语速因子，>1 更慢")
        interval_silence: int = Field(200, description="句间停顿毫秒")
        output: Optional[str] = Field(None, description="输出 wav 路径（缺省自动命名到 outputs/tts_server/）")

    @app.get("/health")
    def health():
        import torch
        return {
            "ok": TTS is not None,
            "version": ARGS.version,
            "model_dir": ARGS.model_dir,
            "device": "cuda" if torch.cuda.is_available() else "cpu",
            "qwen_emo": ARGS.qwen_emo,
            "emotions": list(EMOTION_VECTORS),
        }

    @app.post("/tts")
    def tts(req: TTSRequest):
        if TTS is None:
            from fastapi import HTTPException
            raise HTTPException(503, "模型尚未加载完成")
        if not req.text.strip():
            from fastapi import HTTPException
            raise HTTPException(400, "text 不能为空")

        emo_vector = req.emo_vector
        if emo_vector is None:
            emo_vector = emotion_to_vector(req.emotion, req.intensity)

        spk = req.spk_audio
        if spk and not os.path.isabs(spk):
            spk = os.path.join(ROOT_DIR, spk)
        if not spk or not os.path.isfile(spk):
            from fastapi import HTTPException
            raise HTTPException(400, f"参考音频不存在: {spk}")

        if req.output:
            out_path = os.path.abspath(req.output)
        else:
            os.makedirs(OUT_DIR, exist_ok=True)
            out_path = os.path.join(OUT_DIR, f"tts_{int(time.time() * 1000)}.wav")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        use_emo_text = req.use_emo_text and ARGS.qwen_emo and TTS.qwen_emo is not None
        with TTS_LOCK:  # 显存同一时间只跑一条推理
            out = TTS.infer(
                spk_audio_prompt=spk,
                text=req.text,
                output_path=out_path,
                lang=req.lang,
                emo_vector=emo_vector,
                use_emo_text=use_emo_text,
                emo_text=req.emo_text,
                interval_silence=req.interval_silence,
                duration_factor=req.duration_factor,
            )
        if not out or not os.path.isfile(out_path):
            from fastapi import HTTPException
            raise HTTPException(500, "合成失败，未产出音频文件")
        import soundfile as sf
        info = sf.info(out_path)
        return {"file": out_path, "seconds": round(info.duration, 2), "samplerate": info.samplerate}

    @app.post("/unload")
    def unload():
        import torch
        with TTS_LOCK:
            if TTS is not None:
                for m in [TTS.gpt, TTS.s2mel, TTS.bigvgan]:
                    if m is not None:
                        m.to("cpu")
                torch.cuda.empty_cache()
        return {"ok": True, "msg": "模型已移出 GPU（进程保留）"}

    return app


def main():
    global TTS
    print("=" * 50)
    print(f" 解说 TTS 服务 (IndexTTS-{ARGS.version})  ->  http://{ARGS.host}:{ARGS.port}")
    print(f" 模型目录: {os.path.abspath(ARGS.model_dir)}")
    print("=" * 50)
    if not os.path.isfile(os.path.join(ARGS.model_dir, "config.yaml")):
        print(f"[错误] 模型目录里没有 config.yaml: {ARGS.model_dir}")
        print("       请先下载模型权重（见 README「从零部署」），或用 --model_dir 指定目录。")
        sys.exit(1)

    # Windows 下 uvicorn 默认 proactor 事件循环遇到客户端中断连接会抛
    # ConnectionReset(10054) 异常风暴，累积后进程会无声退出；换成 selector 循环规避。
    import asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn
    app = create_app()

    def _load():
        global TTS
        try:
            TTS = build_tts()
        except Exception as e:
            print(f"[错误] 模型加载失败: {e}")
            import traceback
            traceback.print_exc()

    threading.Thread(target=_load, daemon=True).start()  # 先起 HTTP 再加载，health 可轮询
    uvicorn.run(app, host=ARGS.host, port=ARGS.port, log_level="warning")


if __name__ == "__main__":
    main()
