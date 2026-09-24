# -*- coding: utf-8 -*-
"""解说词生成（步骤 4）：把「约束文档 + 素材」交给 DeepSeek，生成结构化解说词 JSON。

- 约束文档：pipeline/约束文档.md，整体作为 system prompt
- 素材：一段主题文字，或视频理解得到的场景描述
- 输出：{"title": ..., "segments": [{"text", "emotion", "intensity"}, ...]}
- 校验：字段缺失/情感标签非法/强度越界都会被修复或拒绝
- DeepSeek key 为空或调用失败时，可回退到本地 Ollama（config.yaml 里开关）
"""

import json
import os
import re

import requests
import yaml

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))

VALID_EMOTIONS = ["兴奋", "喜悦", "愤怒", "哀伤", "恐惧", "厌恶", "低落", "惊喜", "平静"]


def load_config():
    with open(os.path.join(PIPELINE_DIR, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_constraints_doc():
    path = os.path.join(PIPELINE_DIR, "约束文档.md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_user_message(material: str, style: str, duration_s: int, extra: str = "") -> str:
    """拼装给大模型的用户消息：素材 + 风格 + 时长目标。"""
    # 激情解说语速约每秒 5~6 字，按 5.5 估算总字数
    target_chars = int(duration_s * 5.5)
    seg_hint = max(6, min(20, round(target_chars / 30)))
    msg = (
        f"【解说风格】{style}\n"
        f"【时长要求】最终朗读时长约 {duration_s} 秒，即全文约 {target_chars} 字，"
        f"建议切成 {seg_hint} 段左右（每段 20~40 字）。\n"
    )
    if extra:
        msg += f"【其他要求】{extra}\n"
    msg += f"\n【素材内容】\n{material.strip()}\n"
    msg += "\n请严格遵守约束文档，只输出 JSON。"
    return msg


def _extract_json(text: str):
    """从模型回复里抠出 JSON 对象（容忍代码块包裹）。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"回复里找不到 JSON：{text[:200]}")
    return json.loads(text[start:end + 1])


def validate_script(data: dict) -> dict:
    """校验并尽力修复解说词 JSON，不合格字段直接修正。"""
    if not isinstance(data, dict) or "segments" not in data:
        raise ValueError("JSON 缺少 segments 字段")
    title = str(data.get("title", "激情解说")).strip()[:20] or "激情解说"
    segments = []
    for seg in data["segments"]:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text", "")).strip()
        # 去掉干扰朗读的符号
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
        intensity = max(0.0, min(1.0, intensity))
        segments.append({"text": text, "emotion": emotion, "intensity": round(intensity, 2)})
    if not segments:
        raise ValueError("segments 为空，生成失败")
    return {"title": title, "segments": segments}


def call_deepseek(cfg: dict, system_prompt: str, user_msg: str) -> str:
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


def call_ollama(cfg: dict, system_prompt: str, user_msg: str) -> str:
    ob = cfg["deepseek"].get("fallback_ollama", {})
    body = {
        "model": ob.get("model", "qwen3:14b"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 1.0},
        "keep_alive": 0,  # 用完立刻释放显存，给 TTS 让路
    }
    resp = requests.post(f"{ob.get('host', 'http://127.0.0.1:11434')}/api/chat",
                         json=body, timeout=ob.get("timeout_s", 300))
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def generate_script(material: str, style: str = "激情解说（足球/电竞赛事解说风格）",
                    duration_s: int = 60, extra: str = "") -> dict:
    """主入口：素材 → 解说词 dict。优先 DeepSeek，失败回退 Ollama。"""
    cfg = load_config()
    system_prompt = load_constraints_doc()
    user_msg = build_user_message(material, style, duration_s, extra)

    api_key = cfg["deepseek"].get("api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    fallback = cfg["deepseek"].get("fallback_ollama", {})
    errors = []

    if api_key:
        try:
            print(">> [解说词] 调用 DeepSeek 生成 ...")
            raw = call_deepseek(cfg, system_prompt, user_msg)
            return validate_script(_extract_json(raw))
        except Exception as e:
            errors.append(f"DeepSeek: {e}")
            print(f">> [解说词] DeepSeek 失败：{e}")
            if not (fallback.get("enabled") and _ollama_alive(fallback)):
                raise
    else:
        print(">> [解说词] 未配置 DeepSeek API key（pipeline/config.yaml 或环境变量 DEEPSEEK_API_KEY），"
              "改用本地 Ollama 兜底。")
        if not (fallback.get("enabled") and _ollama_alive(fallback)):
            raise RuntimeError("没有 DeepSeek key 且本地 Ollama 不可用，无法生成解说词")

    print(f">> [解说词] 用本地 Ollama（{fallback.get('model')}）生成 ...")
    raw = call_ollama(cfg, system_prompt, user_msg)
    script = validate_script(_extract_json(raw))
    if errors:
        print(">> [解说词] 注意：本次结果来自本地兜底模型，配置 DeepSeek key 后效果更佳")
    return script


def _ollama_alive(fallback: dict) -> bool:
    try:
        requests.get(f"{fallback.get('host', 'http://127.0.0.1:11434')}/api/tags", timeout=5)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # 快速自测：python script_gen.py "素材文字"
    import sys
    material = sys.argv[1] if len(sys.argv) > 1 else "一支学生团队深夜完成机器人比赛调试，最终拿下省赛冠军。"
    out = generate_script(material, duration_s=45)
    print(json.dumps(out, ensure_ascii=False, indent=2))
