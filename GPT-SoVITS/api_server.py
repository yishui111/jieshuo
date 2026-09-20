# -*- coding: utf-8 -*-
"""GPT-SoVITS 引导式网页控制台服务。

在 api_v2.py 的全部接口之上增加：
  GET /                引导式网页控制台（webui/index.html）
  GET /health          服务健康检查（含当前模型、设备、支持语言等）
  GET /list_resources  可用参考音频 / GPT、SoVITS 权重列表
  GET /ref_audio       参考音频试听
服务就绪后自动打开浏览器。

启动方式与 api_v2.py 完全一致（参数也一致）：
  python api_server.py -a 127.0.0.1 -p 9885 -c GPT_SoVITS/configs/tts_infer.yaml
"""
import os
import sys
import threading
import webbrowser

# 导入 api_v2 会解析同一套命令行参数并加载 TTS 模型（必须先于本文件其他路由定义）
import api_v2

from fastapi import HTTPException
from fastapi.responses import FileResponse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(ROOT_DIR, "webui", "index.html")

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
REF_AUDIO_DIRS = ["参考音频", "asset"]
GPT_WEIGHT_DIRS = ["GPT_weights", "GPT_weights_v2", "GPT_weights_v3", "GPT_weights_v4"]
SOVITS_WEIGHT_DIRS = ["SoVITS_weights", "SoVITS_weights_v2", "SoVITS_weights_v3", "SoVITS_weights_v4"]


def _abs(path: str) -> str:
    """后端内部路径统一转绝对路径，接口收到的相对路径按项目根目录解析。"""
    if path and not os.path.isabs(path):
        return os.path.join(ROOT_DIR, path)
    return path


def _safe_audio_file(path: str):
    path = _abs(path)
    if not path or os.path.splitext(path)[1].lower() not in AUDIO_EXTS or not os.path.isfile(path):
        return None
    return path


def _scan_audio_dir(dir_name: str):
    base = os.path.join(ROOT_DIR, dir_name)
    found = []
    if not os.path.isdir(base):
        return found
    for name in sorted(os.listdir(base)):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in AUDIO_EXTS:
            continue
        full = os.path.join(base, name)
        prompt_text = ""
        txt = os.path.join(base, stem + ".txt")
        if os.path.isfile(txt):
            try:
                with open(txt, "r", encoding="utf-8-sig", errors="ignore") as f:
                    prompt_text = f.read().strip()
            except OSError:
                pass
        found.append({"name": name, "path": full, "prompt_text": prompt_text})
    return found


def _scan_weight_dirs(dir_names: list, exts: set):
    found = []
    for d in dir_names:
        base = os.path.join(ROOT_DIR, d)
        if not os.path.isdir(base):
            continue
        for cur, _dirs, files in os.walk(base):
            for name in sorted(files):
                if os.path.splitext(name)[1].lower() in exts:
                    found.append({"name": name, "path": os.path.join(cur, name)})
    return found


@api_v2.APP.get("/", include_in_schema=False)
async def index():
    return FileResponse(INDEX_HTML, media_type="text/html")


@api_v2.APP.get("/health", include_in_schema=False)
async def health():
    cfg = api_v2.tts_pipeline.configs
    return {
        "status": "ok",
        "version": cfg.version,
        "device": str(cfg.device),
        "is_half": bool(cfg.is_half),
        "gpt_weights": cfg.t2s_weights_path,
        "sovits_weights": cfg.vits_weights_path,
        "languages": list(cfg.languages),
        "cut_methods": list(api_v2.cut_method_names),
    }


@api_v2.APP.get("/list_resources", include_in_schema=False)
async def list_resources():
    ref_audios = []
    seen = set()
    for d in REF_AUDIO_DIRS:
        for item in _scan_audio_dir(d):
            if item["path"] not in seen:
                seen.add(item["path"])
                ref_audios.append(item)
    return {
        "ref_audios": ref_audios,
        "ref_dirs": [d for d in REF_AUDIO_DIRS if os.path.isdir(os.path.join(ROOT_DIR, d))],
        "gpt_weights": _scan_weight_dirs(GPT_WEIGHT_DIRS, {".ckpt"}),
        "sovits_weights": _scan_weight_dirs(SOVITS_WEIGHT_DIRS, {".pth"}),
    }


@api_v2.APP.get("/ref_audio", include_in_schema=False)
async def ref_audio(path: str = None):
    real = _safe_audio_file(path)
    if real is None:
        raise HTTPException(status_code=404, detail="参考音频不存在或格式不支持")
    media = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
             ".ogg": "audio/ogg", ".m4a": "audio/mp4"}[os.path.splitext(real)[1].lower()]
    return FileResponse(real, media_type=media)


@api_v2.APP.on_event("startup")
async def _open_browser_when_ready():
    host = api_v2.host
    if host in (None, "", "None", "0.0.0.0", "::"):
        host = "127.0.0.1"

    def _open():
        url = f"http://{host}:{api_v2.port}/"
        print(f"引导式控制台 -> {url} （如未自动打开，请手动访问）")
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"自动打开浏览器失败：{e}")

    threading.Timer(1.5, _open).start()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app=api_v2.APP, host=api_v2.host, port=api_v2.port, workers=1)
