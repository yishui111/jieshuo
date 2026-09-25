# -*- coding: utf-8 -*-
"""激情解说统一工作台：一个服务管两个项目。

  项目一 · 专属声音  训练素材 → GPT-SoVITS 训练专属声音 → DeepSeek 改写故事 → 专属声音朗读
  项目二 · 情感解说  IndexTTS-2.5（情绪可调）→ DeepSeek 按约束文档写解说词 → "激情洋溢"朗读

启动：双击根目录 启动工作台.bat，浏览器自动打开 http://127.0.0.1:9610
引擎按需拉起：首次合成时自动启动对应引擎（首次要加载模型，耐心等）。
"""

import json
import os
import threading
import time
import webbrowser

import numpy as np
import requests
import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import train_voice
from deepseek_client import generate_script
from engines import MANAGER, WORK_DIR

with open(os.path.join(WORK_DIR, "config.yaml"), encoding="utf-8") as f:
    import yaml
    CFG = yaml.safe_load(f)

STATIC_DIR = os.path.join(WORK_DIR, "static")
OUTPUT_DIR = os.path.normpath(os.path.join(WORK_DIR, CFG["paths"]["outputs_dir"]))
VOICE_CFG_PATH = os.path.join(WORK_DIR, CFG["paths"]["voice_config"])
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="激情解说工作台")


# ---------- 基础页面 ----------
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ---------- 状态 ----------
@app.get("/api/status")
def api_status():
    deepseek_key = bool(CFG["deepseek"].get("api_key")) or bool(os.environ.get("DEEPSEEK_API_KEY"))
    voice_cfg = load_voice_config()
    return {
        "engines": MANAGER.status_all(),
        "deepseek_configured": deepseek_key,
        "voice": voice_cfg,
        "outputs": list_outputs(),
    }


def load_voice_config() -> dict:
    if os.path.isfile(VOICE_CFG_PATH):
        try:
            with open(VOICE_CFG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def list_outputs() -> list:
    items = []
    for fp in sorted(glob_outputs(), key=os.path.getmtime, reverse=True)[:30]:
        items.append({
            "file": os.path.basename(fp),
            "url": f"/audio/{os.path.basename(fp)}",
            "seconds": round(_duration(fp), 1),
            "time": time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(fp))),
        })
    return items


def glob_outputs():
    import glob
    return glob.glob(os.path.join(OUTPUT_DIR, "*.wav")) + glob.glob(os.path.join(OUTPUT_DIR, "*.mp3"))


def _duration(fp: str) -> float:
    try:
        return sf.info(fp).duration
    except Exception:
        return 0.0


# ---------- 约束文档 ----------
@app.get("/api/constraints")
def get_constraints():
    with open(os.path.join(WORK_DIR, "约束文档.md"), encoding="utf-8") as f:
        return {"content": f.read()}


class ConstraintsBody(BaseModel):
    content: str


@app.post("/api/constraints")
def set_constraints(body: ConstraintsBody):
    with open(os.path.join(WORK_DIR, "约束文档.md"), "w", encoding="utf-8") as f:
        f.write(body.content)
    return {"ok": True}


# ---------- 解说词生成 ----------
class GenScriptBody(BaseModel):
    story: str
    style: str = "激情解说（足球/电竞赛事解说风格）"
    duration: int = 60
    extra: str = ""


@app.post("/api/gen_script")
def api_gen_script(body: GenScriptBody):
    if not body.story.strip():
        raise HTTPException(400, "请先输入故事/素材内容")
    try:
        return generate_script(body.story, style=body.style, duration_s=body.duration,
                               extra=body.extra)
    except Exception as e:
        raise HTTPException(500, f"解说词生成失败：{e}")


# ---------- 合成 ----------
class SynthBody(BaseModel):
    mode: str  # voice | emotion
    script: dict
    preset: str = "激情洋溢"       # 情绪预设（emotion 模式默认值）
    emotion_mode: str = "auto"     # auto=跟随解说词标注 | fixed=统一使用预设情绪
    intensity: float = 0.95
    speed: float = 1.0             # duration_factor 的倒数表达，>1 更快


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


def _safe_name(title: str) -> str:
    import re
    return re.sub(r'[\\/:*?"<>|\s]+', "_", title)[:30] or "解说"


def _concat(wavs: list, out_path: str, gap_ms: int = 260) -> float:
    data, sr, gap = None, None, None
    for w in wavs:
        d, s = sf.read(w, dtype="float32")
        if d.ndim > 1:
            d = d.mean(axis=1)
        if data is None:
            data, sr = d, s
            gap = np.zeros(int(sr * gap_ms / 1000), dtype="float32")
        else:
            if s != sr:
                raise ValueError(f"采样率不一致：{w}")
            data = np.concatenate([data, gap, d])
    sf.write(out_path, data, sr)
    return len(data) / sr


def _synth_index_tts(seg_text: str, vec: list, spk: str, speed: float = 1.0) -> str:
    base = MANAGER.get("index_tts").conf["health"].replace("/health", "")
    out = os.path.join(OUTPUT_DIR, "segments", f"seg_{time.time_ns()}.wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    t = CFG["tts"]["index_tts"]
    r = requests.post(f"{base}/tts", json={
        "text": seg_text, "emo_vector": vec, "spk_audio": spk,
        "lang": t.get("lang", "zh_CN"),
        "interval_silence": t.get("interval_silence_ms", 260),
        "duration_factor": max(0.6, min(1.6, 1.0 / max(0.5, speed))),
        "output": out,
    }, timeout=t.get("timeout_s", 600))
    r.raise_for_status()
    return r.json()["file"]


def _synth_gptsovits(seg_text: str, ref_audio: str, prompt_text: str) -> str:
    base = MANAGER.get("gpt_sovits").conf["health"].replace("/health", "")
    out = os.path.join(OUTPUT_DIR, "segments", f"seg_{time.time_ns()}.wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    t = CFG["tts"]["gpt_sovits"]
    r = requests.post(f"{base}/tts", json={
        "text": seg_text,
        "text_lang": t.get("text_lang", "zh"),
        "ref_audio_path": ref_audio,
        "prompt_text": prompt_text,
        "prompt_lang": t.get("prompt_lang", "zh"),
        "text_split_method": "cut0",
        "media_type": "wav",
        "streaming_mode": False,
    }, timeout=t.get("timeout_s", 600))
    r.raise_for_status()
    with open(out, "wb") as f:
        f.write(r.content)
    return out


def _set_gptsovits_weights(voice_cfg: dict):
    base = MANAGER.get("gpt_sovits").conf["health"].replace("/health", "")
    for ep, path in [("/set_sovits_weights", voice_cfg.get("sovits_weights")),
                     ("/set_gpt_weights", voice_cfg.get("gpt_weights"))]:
        if not path:
            continue
        r = requests.get(f"{base}{ep}", params={"weights_path": path}, timeout=300)
        if not r.ok:
            raise RuntimeError(f"切换权重失败 {ep}: {r.text[:200]}")


@app.post("/api/synth")
def api_synth(body: SynthBody):
    script = body.script
    segments = script.get("segments") or []
    if not segments:
        raise HTTPException(400, "解说词为空")
    title = _safe_name(script.get("title", "解说"))
    ts = time.strftime("%Y%m%d_%H%M%S")

    if body.mode == "emotion":
        eng = "index_tts"
        t = CFG["tts"]["index_tts"]
        spk = os.path.normpath(os.path.join(WORK_DIR, t["spk_audio"]))
        preset = t["presets"].get(body.preset, t["presets"]["激情洋溢"])
    else:
        eng = "gpt_sovits"
        voice = load_voice_config()
        if not voice.get("sovits_weights"):
            raise HTTPException(400, "还没有专属声音：请先在「项目一 · 声音训练」里完成训练")
        ref_audio = voice.get("ref_audio", "")
        prompt_text = voice.get("prompt_text", "")

    # 引擎就绪（首次会拉起引擎并加载模型）
    if not MANAGER.ensure(eng, timeout_s=2400):
        raise HTTPException(503, f"引擎 {eng} 启动失败，请查看工作台日志")

    if body.mode == "voice":
        try:
            _set_gptsovits_weights(voice)
        except Exception as e:
            raise HTTPException(500, f"加载专属声音失败：{e}")

    wavs = []
    total = len(segments)
    for i, seg in enumerate(segments, 1):
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        print(f">> [合成] ({i}/{total}) {text[:24]}...", flush=True)
        if body.mode == "emotion":
            if body.emotion_mode == "fixed":
                vec = [v * body.intensity for v in preset["vector"]]
            else:
                emo = seg.get("emotion", "兴奋")
                vec = [v * float(seg.get("intensity", body.intensity))
                       for v in EMOTION_VECTORS.get(emo, EMOTION_VECTORS["兴奋"])]
            wavs.append(_synth_index_tts(text, vec, spk, speed=body.speed))
        else:
            wavs.append(_synth_gptsovits(text, ref_audio, prompt_text))

    if not wavs:
        raise HTTPException(500, "没有合成出任何音频")
    final = os.path.join(OUTPUT_DIR, f"{ts}_{title}.wav")
    seconds = _concat(wavs, final, gap_ms=260)
    return {"ok": True, "file": os.path.basename(final),
            "url": f"/audio/{os.path.basename(final)}", "seconds": round(seconds, 1)}


def ref_audio_override(self, voice):
    return voice.get("ref_audio", "")


SynthBody.ref_audio_override = ref_audio_override  # 简单挂载，避免再建 dataclass


# ---------- 音频与历史 ----------
@app.get("/audio/{name}")
def audio(name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400)
    fp = os.path.join(OUTPUT_DIR, name)
    if not os.path.isfile(fp):
        raise HTTPException(404)
    return FileResponse(fp)


@app.get("/api/ref_audio_file")
def ref_audio_file(path: str):
    """专属声音参考音频试听（限定训练数据目录内）。"""
    fp = os.path.normpath(path)
    if not fp.startswith(os.path.join(WORK_DIR, "训练数据")) and not fp.startswith(
            os.path.normpath(os.path.join(WORK_DIR, "..", "训练素材"))):
        raise HTTPException(400)
    if not os.path.isfile(fp):
        raise HTTPException(404)
    return FileResponse(fp)


# ---------- 引擎管理 ----------
@app.post("/api/engine/{name}/start")
def engine_start(name: str):
    if name not in MANAGER.engines:
        raise HTTPException(404)
    MANAGER.get(name).start()
    return {"ok": True, "status": MANAGER.status_all()}


@app.post("/api/engine/{name}/stop")
def engine_stop(name: str):
    if name not in MANAGER.engines:
        raise HTTPException(404)
    MANAGER.get(name).stop()
    return {"ok": True, "status": MANAGER.status_all()}


@app.get("/api/engine/{name}/log")
def engine_log(name: str, n: int = 50):
    if name not in MANAGER.engines:
        raise HTTPException(404)
    return {"log": MANAGER.get(name).log_tail(n)}


# ---------- 声音训练（项目一） ----------
@app.get("/api/train/materials")
def train_materials():
    return train_voice.list_materials()


@app.post("/api/train/start")
def train_start():
    t = CFG["training"]
    result = train_voice.start_training(
        exp_name=t["default_exp_name"],
        sovits_epochs=t["sovits_epochs"], gpt_epochs=t["gpt_epochs"],
        sovits_bs=t["sovits_batch_size"], gpt_bs=t["gpt_batch_size"],
        save_every=t["save_every_epoch"])
    if not result.get("ok"):
        raise HTTPException(400, result.get("msg"))
    return result


@app.get("/api/train/status")
def train_status():
    st = train_voice.state()
    tail = ""
    if st.get("log_file") and os.path.isfile(st["log_file"]):
        with open(st["log_file"], encoding="utf-8", errors="replace") as f:
            tail = "".join(f.readlines()[-30:])
    st["log_tail"] = tail
    st["trained"] = _trained_models()
    return st


def _trained_models() -> list:
    import glob
    out = []
    for sub, kind in [("SoVITS_weights_v2", "sovits"), ("GPT_weights_v2", "gpt")]:
        folder = os.path.join(GSV_ROOT, sub)
        for fp in sorted(glob.glob(os.path.join(folder, "*.pth")) +
                         glob.glob(os.path.join(folder, "*.ckpt")), key=os.path.getmtime, reverse=True):
            out.append({"kind": kind, "file": os.path.basename(fp), "path": fp,
                        "mtime": time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(fp)))})
    return out


@app.get("/api/train/log")
def train_log_file():
    return FileResponse(train_voice.state().get("log_file") or os.devnull)


class VoiceSelectBody(BaseModel):
    sovits_weights: str
    gpt_weights: str
    ref_audio: str = ""
    prompt_text: str = ""
    exp_name: str = "我的解说声音"


@app.post("/api/voice/select")
def voice_select(body: VoiceSelectBody):
    """手动启用某个训练产出的声音（写入 voice_config.json，合成时自动切换权重）。"""
    for p in [body.sovits_weights, body.gpt_weights, body.ref_audio]:
        if p and not os.path.isfile(p):
            raise HTTPException(400, f"文件不存在：{p}")
    voice = {"exp_name": body.exp_name, "sovits_weights": body.sovits_weights,
             "gpt_weights": body.gpt_weights, "ref_audio": body.ref_audio,
             "prompt_text": body.prompt_text,
             "trained_at": time.strftime("%F %T")}
    with open(VOICE_CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(voice, f, ensure_ascii=False, indent=2)
    return {"ok": True, "voice": voice}


# ---------- 静态资源 ----------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/audio_dir", StaticFiles(directory=OUTPUT_DIR), name="audio_dir")


def main():
    host = CFG["workbench"]["host"]
    port = CFG["workbench"]["port"]
    print("=" * 56)
    print(" 激情解说 · 统一工作台")
    print(f" 项目一 专属声音（训练+朗读） / 项目二 情感解说（激情洋溢）")
    print(f" http://{host}:{port}")
    print("=" * 56)
    def _open_browser():
        """等端口就绪后再打开浏览器（机器慢时 uvicorn 绑定可能要几十秒）。"""
        import requests as _rq
        for _ in range(60):
            try:
                _rq.get(f"http://{host}:{port}/", timeout=2)
                break
            except Exception:
                time.sleep(2)
        webbrowser.open(f"http://{host}:{port}")
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
