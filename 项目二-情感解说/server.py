# -*- coding: utf-8 -*-
"""项目二 · 情感解说工作台后端（独立服务，端口见 config.yaml 的 workbench.port）。

整个项目的流程：

    ① 故事/素材文字
    ② 约束文档.md + 故事  →  DeepSeek（无 Key 回退本地 Ollama） →  激情解说词 JSON
       （每段 20~40 字，带 emotion 情感标注 + intensity 强度）
    ③ 解说词逐段交给 IndexTTS-2.5 按情绪预设带情感朗读，拼成一条音频
       情绪可调：激情洋溢 / 兴奋 / 愤怒 / 惊喜…；可跟随解说词逐段标注，也可整段统一

接口一览：
  GET  /                     前端页面（static/index.html）
  GET  /api/status           引擎状态 / DeepSeek 是否配置 / 产物列表
  GET  /api/constraints      读约束文档      POST /api/constraints 保存
  POST /api/gen_script       故事 → 解说词（同步，约 10~60 秒）
  POST /api/synth            解说词 → 语音（异步，返回 job_id）
  GET  /api/job/{id}         查询任务进度
  POST /api/engine/index_tts/start|stop     GET /api/engine/index_tts/log
"""

import json
import os
import threading
import time
import traceback
import webbrowser

import numpy as np
import requests
import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deepseek_client import generate_script
from engines import MANAGER, WORK_DIR

with open(os.path.join(WORK_DIR, "config.yaml"), encoding="utf-8") as f:
    import yaml
    CFG = yaml.safe_load(f)

STATIC_DIR = os.path.join(WORK_DIR, "static")
OUTPUT_DIR = os.path.normpath(os.path.join(WORK_DIR, CFG["paths"]["outputs_dir"]))
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="项目二 · 情感解说工作台")

# 情感标签 → IndexTTS 8 维情感向量 [喜, 怒, 哀, 惧, 厌恶, 低落, 惊喜, 平静]
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

# 异步任务表：job_id -> {"stage", "done", "error", "result", "started"}
JOBS = {}
JOBS_LOCK = threading.Lock()


def new_job() -> str:
    with JOBS_LOCK:
        # 只保留最近 20 条任务，防止长期运行时任务表无限增长
        if len(JOBS) > 20:
            for old in sorted(JOBS, key=lambda k: JOBS[k]["started"])[: len(JOBS) - 20]:
                del JOBS[old]
        job_id = time.strftime("%H%M%S") + f"_{len(JOBS) + 1}"
        JOBS[job_id] = {"stage": "排队中", "done": False, "error": "",
                        "result": {}, "started": time.time()}
        return job_id


def set_job(job_id: str, stage: str, **kw):
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["stage"] = stage
        job.update(kw)


# =====================================================================
# 第 1 部分：页面与静态资源
# =====================================================================
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# =====================================================================
# 第 2 部分：状态 / 约束文档
# =====================================================================
@app.get("/api/status")
def api_status():
    return {
        "engines": MANAGER.status_all(),
        "deepseek_configured": bool(CFG["deepseek"].get("api_key")
                                    or os.environ.get("DEEPSEEK_API_KEY")),
        "outputs": _list_outputs(),
    }


def _list_outputs() -> list:
    import glob
    items = []
    for fp in sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.wav")) +
                     glob.glob(os.path.join(OUTPUT_DIR, "*.mp3")),
                     key=os.path.getmtime, reverse=True)[:30]:
        try:
            seconds = round(sf.info(fp).duration, 1)
        except Exception:
            seconds = 0
        items.append({"file": os.path.basename(fp),
                      "url": f"/audio/{os.path.basename(fp)}",
                      "seconds": seconds,
                      "time": time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(fp)))})
    return items


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


# =====================================================================
# 第 3 部分：解说词生成（约束文档 + 故事 → DeepSeek）
# =====================================================================
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
        return generate_script(body.story, style=body.style,
                               duration_s=body.duration, extra=body.extra)
    except Exception as e:
        msg = str(e)
        if "DeepSeek" in msg or "Ollama" in msg:
            msg += ("｜解决办法：打开本项目根目录的 config.yaml，在 deepseek.api_key 填入你的 "
                    "DeepSeek Key（平台 platform.deepseek.com 申请），保存后直接重试，无需重启。")
        raise HTTPException(500, f"解说词生成失败：{msg}")


# =====================================================================
# 第 4 部分：语音合成（异步任务：解说词 → 音频）
# =====================================================================
class SynthBody(BaseModel):
    script: dict
    preset: str = "激情洋溢"    # 整段统一使用的情绪预设
    emotion_mode: str = "auto"  # auto=跟随解说词逐段标注 | fixed=统一用预设
    intensity: float = 0.95
    speed: float = 1.0


@app.post("/api/synth")
def api_synth(body: SynthBody):
    if not (body.script.get("segments") or []):
        raise HTTPException(400, "解说词为空，请先生成解说词")
    job_id = new_job()
    threading.Thread(target=_synth_job, args=(job_id, body), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def api_job(job_id: str):
    with JOBS_LOCK:
        job = json.loads(json.dumps(JOBS.get(job_id, {})))  # 快照
    if not job:
        raise HTTPException(404, "任务不存在")
    job["elapsed"] = round(time.time() - job.get("started", time.time()))
    return job


def _safe_name(title: str) -> str:
    import re
    return re.sub(r'[\\/:*?"<>|\s]+', "_", title)[:30] or "解说"


def _synth_job(job_id: str, body: SynthBody):
    """后台执行：确保引擎就绪 → 按情绪逐段合成 → 拼接成片。所有失败都写进任务状态。"""
    try:
        segments = [s for s in body.script.get("segments", []) if str(s.get("text", "")).strip()]
        title = _safe_name(body.script.get("title", "解说"))
        set_job(job_id, "准备合成")

        t = CFG["tts"]["index_tts"]
        spk = os.path.normpath(os.path.join(WORK_DIR, t["spk_audio"]))
        preset = t["presets"].get(body.preset, t["presets"]["激情洋溢"])

        # 引擎就绪（首次要加载模型，几分钟；阶段实时汇报给页面）
        set_job(job_id, f"启动{MANAGER.get('index_tts').conf.get('label', '引擎')}…（首次加载模型约 3~15 分钟）")
        MANAGER.ensure("index_tts", timeout_s=2400,
                       progress=lambda s: set_job(job_id, f"引擎加载中：{s}"))

        # 逐段合成（引擎若被系统压掉，自动重新拉起并重试当前段）
        wavs = []
        total = len(segments)
        for i, seg in enumerate(segments, 1):
            text = str(seg["text"]).strip()
            set_job(job_id, f"合成中 ({i}/{total})：{text[:16]}…")
            if body.emotion_mode == "fixed":
                vec = [v * body.intensity for v in preset["vector"]]
            else:
                emo = seg.get("emotion", "兴奋")
                base = EMOTION_VECTORS.get(emo, EMOTION_VECTORS["兴奋"])
                vec = [v * float(seg.get("intensity", body.intensity)) for v in base]
            wavs.append(_with_engine_retry(
                job_id, lambda v=vec: _tts_index_tts(text, v, spk, body.speed)))

        # 拼接成片
        set_job(job_id, "拼接成片…")
        final = os.path.join(OUTPUT_DIR, f"{time.strftime('%Y%m%d_%H%M%S')}_{title}.wav")
        data, sr, gap = None, None, None
        for w in wavs:
            d, s = sf.read(w, dtype="float32")
            if d.ndim > 1:
                d = d.mean(axis=1)
            if data is None:
                data, sr = d, s
                gap = np.zeros(int(sr * 0.26), dtype="float32")
            else:
                data = np.concatenate([data, gap, d])
        sf.write(final, data, sr)
        seconds = round(len(data) / sr, 1)

        set_job(job_id, "完成", done=True,
                result={"file": os.path.basename(final), "url": f"/audio/{os.path.basename(final)}",
                        "seconds": seconds})
    except Exception as e:
        traceback.print_exc()
        set_job(job_id, "失败", done=True, error=str(e))


def _with_engine_retry(job_id: str, fn):
    """调用引擎合成；连接被断开（引擎被系统压掉）时重新拉起引擎并重试一次。"""
    try:
        return fn()
    except requests.ConnectionError:
        set_job(job_id, "引擎连接中断，自动重启引擎并重试…")
        MANAGER.ensure("index_tts", timeout_s=2400,
                       progress=lambda s: set_job(job_id, f"引擎加载中：{s}"))
        return fn()


def _tts_index_tts(text: str, vec: list, spk: str, speed: float) -> str:
    """调 IndexTTS-2.5 引擎合成一段，返回 wav 路径。"""
    base = MANAGER.get("index_tts").conf["health"].replace("/health", "")
    out = os.path.join(WORK_DIR, "logs", "segments", f"seg_{time.time_ns()}.wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    t = CFG["tts"]["index_tts"]
    r = requests.post(f"{base}/tts", json={
        "text": text, "emo_vector": vec, "spk_audio": spk,
        "lang": t.get("lang", "zh_CN"),
        "interval_silence": t.get("interval_silence_ms", 260),
        "duration_factor": max(0.6, min(1.6, 1.0 / max(0.5, speed))),
        "output": out,
    }, timeout=t.get("timeout_s", 600))
    r.raise_for_status()
    return r.json()["file"]


@app.get("/audio/{name}")
def audio(name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400)
    fp = os.path.join(OUTPUT_DIR, name)
    if not os.path.isfile(fp):
        raise HTTPException(404)
    return FileResponse(fp)


# =====================================================================
# 第 5 部分：引擎手动管理
# =====================================================================
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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main():
    host = CFG["workbench"]["host"]
    port = int(CFG["workbench"]["port"])

    def _open_browser():
        if os.environ.get("NO_BROWSER"):  # 测试/无人值守时设置，不自动弹页面
            return
        import requests as rq
        for _ in range(90):  # 机器慢时端口绑定可能要几十秒，等就绪再开浏览器
            try:
                rq.get(f"http://{host}:{port}/", timeout=2)
                break
            except Exception:
                time.sleep(2)
        webbrowser.open(f"http://{host}:{port}")

    print("=" * 56)
    print(" 项目二 · 情感解说工作台（IndexTTS-2.5 激情洋溢）")
    print(f" 页面地址: http://{host}:{port}  （浏览器将自动打开）")
    print(" 语音引擎在点「朗读」时自动启动；关闭本窗口即停止工作台")
    print("=" * 56)
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
