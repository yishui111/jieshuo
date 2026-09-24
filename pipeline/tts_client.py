# -*- coding: utf-8 -*-
"""语音合成客户端（步骤 5）：把解说词逐段交给解说 TTS 服务，拼成一条完整音频。

- 每段按 emotion/intensity 转 8 维情感向量后调 POST /tts
- 段与段之间插入停顿（config: tts.interval_silence_ms）
- 拼接输出：解说音频/<标题>_<时间戳>.wav（可选 -mp3 转码）
"""

import os
import subprocess
import time

import requests
import soundfile as sf
import numpy as np

# 情感标签 -> 8 维向量基值 [喜, 怒, 哀, 惧, 厌恶, 低落, 惊喜, 平静]（与服务端一致）
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


def wait_until_ready(base_url: str, timeout_s: int = 7200, spk_audio: str = "") -> dict:
    """轮询 /health，直到模型加载完成；顺带校验参考音频是否存在。"""
    print(f">> [TTS] 等待解说 TTS 服务就绪（{base_url}，首次加载模型可能要几分钟）...")
    t0 = time.time()
    last_err = None
    while time.time() - t0 < timeout_s:
        try:
            r = requests.get(f"{base_url}/health", timeout=5)
            if r.ok and r.json().get("ok"):
                if spk_audio and not os.path.isfile(spk_audio):
                    raise RuntimeError(f"参考音频不存在: {spk_audio}")
                print(f">> [TTS] 服务就绪（耗时 {time.time() - t0:.0f}s）")
                return r.json()
            last_err = f"HTTP {r.status_code}: {r.text[:100]}"
        except requests.RequestException as e:
            last_err = str(e)[:200]
        time.sleep(5)
    raise RuntimeError(f"TTS 服务在 {timeout_s}s 内未就绪，最后状态：{last_err}\n"
                       "请先运行 index-tts\\启动_TTS服务.bat")


def synth_segments(script: dict, cfg: dict) -> list:
    """逐段合成，返回 [(段序号, wav路径), ...]。"""
    t = cfg["tts"]
    base = t["server"].rstrip("/")
    spk = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), t["spk_audio"]))
    out_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            t.get("segments_dir", "segments")))
    os.makedirs(out_dir, exist_ok=True)
    timeout = t.get("timeout_s", 600)

    wavs = []
    total = len(script["segments"])
    for i, seg in enumerate(script["segments"], 1):
        emo = seg.get("emotion", "兴奋")
        vec = EMOTION_VECTORS.get(emo, EMOTION_VECTORS["兴奋"])
        intensity = float(seg.get("intensity", 0.9))
        vec = [round(v * intensity, 3) for v in vec]
        out_path = os.path.join(out_dir, f"seg_{i:02d}_{emo}.wav")
        print(f">> [TTS] ({i}/{total}) [{emo} {intensity}] {seg['text'][:24]}...")
        resp = requests.post(f"{base}/tts", json={
            "text": seg["text"],
            "emo_vector": vec,
            "spk_audio": spk,
            "lang": t.get("lang", "zh_CN"),
            "interval_silence": t.get("interval_silence_ms", 260),
            "output": out_path,
        }, timeout=timeout)
        resp.raise_for_status()
        wavs.append(out_path)
    return wavs


def concat_wavs(wavs: list, out_path: str, gap_ms: int = 260) -> float:
    """把各段 wav 拼成一条，段间插静音，返回总时长秒。"""
    data, sr = None, None
    gap = None
    for w in wavs:
        d, s = sf.read(w, dtype="float32")
        if d.ndim > 1:
            d = d.mean(axis=1)
        if data is None:
            data, sr = d, s
            gap = np.zeros(int(sr * gap_ms / 1000), dtype="float32")
        else:
            if s != sr:
                raise ValueError(f"采样率不一致: {w} 是 {s}，之前是 {sr}")
            data = np.concatenate([data, gap, d])
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sf.write(out_path, data, sr)
    return len(data) / sr


def to_mp3(wav_path: str) -> str:
    mp3 = os.path.splitext(wav_path)[0] + ".mp3"
    r = subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-i", wav_path,
                        "-b:a", "192k", mp3], capture_output=True)
    if r.returncode == 0 and os.path.isfile(mp3):
        return mp3
    return ""
