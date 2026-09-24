# -*- coding: utf-8 -*-
"""视频理解（可选输入路径）：把视频变成一段「素材描述」，供解说词生成使用。

流程：ffmpeg 按时间均匀抽帧 -> Ollama 本地视觉模型（多帧一次描述）-> 场景描述文字。
描述完成后立即卸载视觉模型显存（keep_alive=0），把显卡让给后续的 TTS 合成。

没有可用的视觉模型时，返回视频元信息描述（时长等），流水线仍可继续（解说词会比较泛）。
"""

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile

import requests


def _ffprobe_duration(video_path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
        capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def extract_frames(video_path: str, max_frames: int, frame_width: int) -> list:
    """按时间均匀抽帧，返回 jpeg 文件路径列表（按时间顺序）。"""
    duration = _ffprobe_duration(video_path)
    n = max(1, min(max_frames, int(duration // 2) or 1))
    tmp_dir = tempfile.mkdtemp(prefix="jieshuo_frames_")
    frames = []
    for i in range(n):
        t = duration * (i + 0.5) / n
        out = os.path.join(tmp_dir, f"frame_{i:02d}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "quiet", "-ss", f"{t:.2f}", "-i", video_path,
             "-frames:v", "1", "-vf", f"scale={frame_width}:-2", "-q:v", "3", out],
            check=True)
        if os.path.isfile(out):
            frames.append(out)
    return frames


def _pick_vision_model(cfg_vlm: str, host: str) -> str:
    """优先用配置的模型；没有就在已安装模型里自动找一个带视觉投影(clip)的。"""
    tags = requests.get(f"{host}/api/tags", timeout=5).json().get("models", [])
    names = {m["name"] for m in tags}
    if cfg_vlm in names:
        return cfg_vlm
    for m in tags:
        families = (m.get("details") or {}).get("families") or []
        if "clip" in families:  # ollama 里视觉模型都带 clip 投影
            return m["name"]
    return ""


def describe_video(video_path: str, video_cfg: dict, ollama_cfg: dict) -> str:
    """主入口：视频文件 -> 素材描述文字。"""
    duration = _ffprobe_duration(video_path)
    base = (f"这是一段时长约 {duration:.0f} 秒的视频"
            f"（文件名：{os.path.basename(video_path)}）。")

    host = ollama_cfg.get("host", "http://127.0.0.1:11434")
    try:
        model = _pick_vision_model(video_cfg.get("vlm_model", ""), host)
    except Exception:
        model = ""
    if not model:
        print(f">> [视频] 本地 Ollama 没有视觉模型（建议 ollama pull {video_cfg.get('vlm_model', 'qwen3-vl:8b')}），"
              "只提供视频元信息，解说词会更依赖主题文字。")
        return base + "无法读取画面内容。"

    print(f">> [视频] 抽帧并用本地视觉模型 {model} 理解画面 ...")
    frames = extract_frames(video_path, video_cfg.get("max_frames", 10),
                            video_cfg.get("frame_width", 768))
    if not frames:
        return base + "抽帧失败，无法读取画面内容。"

    images = []
    for f in frames:
        with open(f, "rb") as fp:
            images.append(base64.b64encode(fp.read()).decode())
    shutil.rmtree(os.path.dirname(frames[0]), ignore_errors=True)

    timeout = video_cfg.get("vlm_timeout_s", 300)

    # 一次喂太多帧可能超出视觉模型上下文（HTTP 400），自动减帧重试
    while True:
        prompt = (
            f"以下 {len(images)} 张图是同一个视频按时间顺序抽取的画面。"
            "请按时间顺序描述这个视频：场景地点、人物或物体、关键动作与事件、"
            "画面中出现的比分/文字（如有）、整体氛围。条理清晰，300 字以内，"
            "只描述画面里能确认的内容。"
        )
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": images}],
            "stream": False,
            "think": False,
            "keep_alive": 0,  # 立刻释放显存给 TTS
            "options": {"temperature": 0.3, "num_ctx": 8192},
        }
        resp = requests.post(f"{host}/api/chat", json=body, timeout=timeout)
        if resp.status_code == 400 and len(images) > 2:
            images = images[: max(2, len(images) // 2)]
            print(f">> [视频] 上下文超限，减到 {len(images)} 帧重试 ...")
            continue
        resp.raise_for_status()
        break
    desc = resp.json()["message"]["content"].strip()
    desc = re.sub(r"<think>.*?</think>", "", desc, flags=re.S).strip()
    print(f">> [视频] 画面理解完成（{len(desc)} 字），显存已释放")
    return f"{base}画面内容：{desc}"


if __name__ == "__main__":
    import sys
    import yaml
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"),
              encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    print(describe_video(sys.argv[1], cfg["video"], cfg["deepseek"]["fallback_ollama"]))
