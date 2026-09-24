# -*- coding: utf-8 -*-
"""激情解说一键流水线：

    输入（主题文字 或 视频文件）
      -> [视频输入] ffmpeg 抽帧 + 本地视觉模型理解画面（pipeline/video_info.py）
      -> DeepSeek 按「约束文档」生成结构化解说词（pipeline/script_gen.py，步骤3/4）
      -> 解说 TTS 服务逐段带情感合成并拼接成片（pipeline/tts_client.py，步骤5）

用法示例：
    python jieshuo.py --text "昨晚的世界杯预选赛，国足绝杀" --duration 60
    python jieshuo.py --video "D:\\比赛录像.mp4" --style "足球解说" --duration 90
    python jieshuo.py --script "解说音频\\xxx.json"          # 改过解说词后重新合成
    python jieshuo.py --text "..." --no-tts                 # 只生成解说词不合成
不带参数运行进入交互模式（可拖入视频文件）。
"""

import argparse
import json
import os
import re
import sys
import time

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPELINE_DIR)

import yaml

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".ts", ".webm", ".m4v"}


def parse_args():
    p = argparse.ArgumentParser(description="激情解说一键流水线：文字/视频 → 解说词 → 激情音频")
    p.add_argument("--text", help="解说主题/素材文字")
    p.add_argument("--video", help="视频文件路径（抽帧理解画面后生成解说词）")
    p.add_argument("--style", default="激情解说（足球/电竞赛事解说风格）", help="解说风格")
    p.add_argument("--duration", type=int, default=60, help="目标朗读时长（秒）")
    p.add_argument("--extra", default="", help="其他要求，如『重点强调防守』")
    p.add_argument("--script", help="已有的解说词 JSON（跳过生成，直接合成）")
    p.add_argument("--no-tts", action="store_true", help="只生成解说词，不合成音频")
    p.add_argument("--mp3", action="store_true", help="同时输出 mp3")
    p.add_argument("--out", default="", help="输出目录（默认 config.yaml 的 output.dir）")
    return p.parse_args()


def interactive_input(args):
    """无参数运行时，让用户直接输入主题文字或拖入视频。"""
    print("=" * 56)
    print(" 激情解说一键生成")
    print(" 输入解说主题文字后回车；或直接把视频文件拖进本窗口")
    print("=" * 56)
    raw = input("主题/视频 > ").strip().strip('"')
    if not raw:
        print("未输入任何内容，退出。")
        sys.exit(1)
    if os.path.isfile(raw) and os.path.splitext(raw)[1].lower() in VIDEO_EXTS:
        args.video = raw
        print(f">> 识别到视频：{raw}")
    else:
        args.text = raw
    style = input(f"解说风格（回车默认：{args.style}）> ").strip()
    if style:
        args.style = style
    return args


def prepare_material(args, cfg) -> str:
    """把输入变成「素材文字」。"""
    if args.video:
        if not os.path.isfile(args.video):
            sys.exit(f"[错误] 视频不存在：{args.video}")
        from video_info import describe_video
        material = describe_video(args.video, cfg["video"], cfg["deepseek"]["fallback_ollama"])
        if args.text:
            material += f"\n用户补充说明：{args.text}"
        return material
    return args.text


def save_script_files(script: dict, out_dir: str, ts: str):
    """解说词落盘：JSON（可改后用 --script 重新合成）+ 可读 Markdown。"""
    stem = re.sub(r'[\\/:*?"<>|\s]+', "_", script["title"])[:30] or "解说词"
    json_path = os.path.join(out_dir, f"{ts}_{stem}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    md_path = os.path.join(out_dir, f"{ts}_{stem}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {script['title']}\n\n")
        for i, seg in enumerate(script["segments"], 1):
            f.write(f"{i}. 【{seg['emotion']} {seg['intensity']:.2f}】{seg['text']}\n")
    return json_path, md_path, stem


def main():
    args = parse_args()
    if not args.text and not args.video and not args.script:
        args = interactive_input(args)

    with open(os.path.join(PIPELINE_DIR, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    out_dir = os.path.normpath(os.path.join(PIPELINE_DIR, args.out or cfg["output"]["dir"]))
    os.makedirs(out_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    # 1) 解说词：现成的 / 视频理解 + 大模型生成
    if args.script:
        with open(args.script, encoding="utf-8") as f:
            script = json.load(f)
        print(f">> [解说词] 使用已有解说词：{args.script}")
    else:
        material = prepare_material(args, cfg)
        print(f">> [素材] {material[:120]}{'...' if len(material) > 120 else ''}")
        from script_gen import generate_script
        script = generate_script(material, style=args.style, duration_s=args.duration,
                                 extra=args.extra)

    json_path, md_path, stem = save_script_files(script, out_dir, ts)
    n_chars = sum(len(s["text"]) for s in script["segments"])
    print(f">> [解说词]《{script['title']}》共 {len(script['segments'])} 段 / {n_chars} 字")
    print(f">> [解说词] 已保存：{json_path}")
    print(f">> [解说词] 已保存：{md_path}")
    if args.no_tts:
        return

    # 2) 语音合成：等服务就绪 -> 逐段合成 -> 拼接
    from tts_client import wait_until_ready, synth_segments, concat_wavs, to_mp3
    wait_until_ready(cfg["tts"]["server"], spk_audio=os.path.normpath(
        os.path.join(PIPELINE_DIR, cfg["tts"]["spk_audio"])))
    t0 = time.time()
    wavs = synth_segments(script, cfg)
    final_path = os.path.join(out_dir, f"{ts}_{stem}.wav")
    seconds = concat_wavs(wavs, final_path, gap_ms=cfg["tts"].get("interval_silence_ms", 260))
    print(f">> [音频] 合成完成：{final_path}（{seconds:.1f} 秒，纯合成 {time.time() - t0:.0f}s）")

    if args.mp3:
        mp3 = to_mp3(final_path)
        if mp3:
            print(f">> [音频] 已转码：{mp3}")

    print("\n全部完成。解说词 JSON 可手动修改后重新合成：")
    print(f"  python jieshuo.py --script \"{json_path}\"")


if __name__ == "__main__":
    main()
