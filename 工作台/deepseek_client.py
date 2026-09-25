# -*- coding: utf-8 -*-
"""DeepSeek 解说词生成：约束文档 + 故事/素材 → 结构化解说词 JSON（可回退本地 Ollama）。"""

import json
import os
import re

import requests

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
VALID_EMOTIONS = ["兴奋", "喜悦", "愤怒", "哀伤", "恐惧", "厌恶", "低落", "惊喜", "平静"]


def load_config():
    import yaml
    with open(os.path.join(WORK_DIR, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_constraints_doc():
    with open(os.path.join(WORK_DIR, "约束文档.md"), encoding="utf-8") as f:
        return f.read()


def build_user_message(story: str, style: str, duration_s: int, extra: str = "") -> str:
    target_chars = int(duration_s * 5.5)
    seg_hint = max(6, min(20, round(target_chars / 30)))
    msg = (
        f"【解说风格】{style}\n"
        f"【时长要求】最终朗读时长约 {duration_s} 秒，即全文约 {target_chars} 字，"
        f"建议切成 {seg_hint} 段左右（每段 20~40 字）。\n"
    )
    if extra:
        msg += f"【其他要求】{extra}\n"
    msg += f"\n【故事/素材】\n{story.strip()}\n"
    msg += "\n请严格遵守约束文档，把它改写成激情解说词，只输出 JSON。"
    return msg


def _extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"回复里找不到 JSON：{text[:200]}")
    return json.loads(text[start:end + 1])


def validate_script(data: dict) -> dict:
    if not isinstance(data, dict) or "segments" not in data:
        raise ValueError("JSON 缺少 segments 字段")
    title = str(data.get("title", "激情解说")).strip()[:20] or "激情解说"
    segments = []
    for seg in data["segments"]:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text", "")).strip()
        text = re.sub(r"[*#`>\[\]{}]|解说词[:：]|第[一二三四五六七八九十]+段[:：]?", "", text).strip()
        if not text:
            continue
        emotion = str(seg.get("emotion", "兴奋")).strip()
        if emotion not in VALID_EMOTIONS:
            emotion = "兴奋"
        try:
            intensity = float(seg.get("intensity", 0.9))
        except (TypeError, ValueError):
            intensity = 0.9
        segments.append({"text": text, "emotion": emotion,
                         "intensity": round(max(0.0, min(1.0, intensity)), 2)})
    if not segments:
        raise ValueError("segments 为空，生成失败")
    return {"title": title, "segments": segments}


def _call_deepseek(cfg, system_prompt, user_msg):
    ds = cfg["deepseek"]
    resp = requests.post(
        f"{ds['api_base'].rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {ds['api_key']}"},
        json={
            "model": ds.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "temperature": ds.get("temperature", 1.3),
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
        },
        timeout=ds.get("timeout_s", 180),
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_ollama(cfg, system_prompt, user_msg):
    ob = cfg["deepseek"]["fallback_ollama"]
    resp = requests.post(
        f"{ob.get('host', 'http://127.0.0.1:11434')}/api/chat",
        json={
            "model": ob.get("model", "qwen3.5:4b"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 1.0},
            "keep_alive": 0,
        },
        timeout=ob.get("timeout_s", 300),
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _ollama_alive(cfg):
    ob = cfg["deepseek"].get("fallback_ollama", {})
    try:
        requests.get(f"{ob.get('host', 'http://127.0.0.1:11434')}/api/tags", timeout=5)
        return True
    except Exception:
        return False


def generate_script(story: str, style: str = "激情解说（足球/电竞赛事解说风格）",
                    duration_s: int = 60, extra: str = "") -> dict:
    """主入口：故事/素材 → 解说词 dict。优先 DeepSeek，失败回退本地 Ollama。"""
    cfg = load_config()
    system_prompt = load_constraints_doc()
    user_msg = build_user_message(story, style, duration_s, extra)

    api_key = cfg["deepseek"].get("api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    fallback = cfg["deepseek"].get("fallback_ollama", {})
    used_fallback = False

    if api_key:
        try:
            return validate_script(_extract_json(_call_deepseek(cfg, system_prompt, user_msg)))
        except Exception as e:
            print(f">> [解说词] DeepSeek 调用失败：{e}，尝试本地兜底")
            if not (fallback.get("enabled") and _ollama_alive(cfg)):
                raise
    else:
        if not (fallback.get("enabled") and _ollama_alive(cfg)):
            raise RuntimeError("未配置 DeepSeek API key，且本地 Ollama 不可用，无法生成解说词")
        used_fallback = True

    script = validate_script(_extract_json(_call_ollama(cfg, system_prompt, user_msg)))
    script["_notice"] = "本次解说词由本地 Ollama 兜底生成（配置 DeepSeek key 后文采更佳）" if used_fallback else ""
    return script


if __name__ == "__main__":
    import sys
    story = sys.argv[1] if len(sys.argv) > 1 else "一支学生团队深夜完成机器人比赛调试，最终拿下省赛冠军。"
    print(json.dumps(generate_script(story, duration_s=45), ensure_ascii=False, indent=2))
