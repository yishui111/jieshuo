# -*- coding: utf-8 -*-
"""引擎管理：按需拉起/停止两个 TTS 引擎子进程，健康检查，日志落盘。

- index_tts : IndexTTS-2.5 情感解说引擎（项目二），端口 9602
- gpt_sovits: GPT-SoVITS 推理 API（项目一，专属声音），端口 9885
两个引擎都把 HF/ModelScope 缓存钉在 工作台/model_cache/ 内，不占 C 盘。
"""

import os
import subprocess
import threading
import time

import requests

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(WORK_DIR, "logs")


def _load_cfg():
    import yaml
    with open(os.path.join(WORK_DIR, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def localized_env(extra: dict = None) -> dict:
    """继承当前环境，把 HF/ModelScope 缓存指到项目内。"""
    cfg = _load_cfg()
    cache = os.path.normpath(os.path.join(WORK_DIR, cfg["paths"]["model_cache_dir"]))
    env = os.environ.copy()
    env["HF_HOME"] = os.path.join(cache, "huggingface")
    env["MODELSCOPE_CACHE"] = os.path.join(cache, "modelscope")
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    if extra:
        env.update(extra)
    return env


class Engine:
    def __init__(self, name: str, conf: dict):
        self.name = name
        self.conf = conf
        self.proc = None
        self.log_path = os.path.join(LOG_DIR, f"engine_{name}.log")
        self.lock = threading.Lock()

    def _resolve(self, path: str) -> str:
        return os.path.normpath(os.path.join(WORK_DIR, path))

    def status(self) -> str:
        if self.proc is not None and self.proc.poll() is None:
            return "ready" if self.healthy() else "starting"
        return "stopped"

    def healthy(self, timeout: int = 4) -> bool:
        try:
            r = requests.get(self.conf["health"], timeout=timeout)
            if not r.ok:
                return False
            field = self.conf.get("ready_field")
            data = r.json()
            return bool(data.get(field, True)) if field else True
        except Exception:
            return False

    def start(self, wait_s: int = 0):
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                return
            cwd = self._resolve(self.conf["cwd"])
            # cmd.exe 无法直接执行 ../ 开头、含正斜杠的相对路径：把可执行文件先解析成绝对路径
            parts = self.conf["cmd"].split(" ", 1)
            exe = os.path.normpath(os.path.join(WORK_DIR, self.conf["cwd"], parts[0]))
            cmd = f'"{exe}" {parts[1]}' if len(parts) > 1 else f'"{exe}"'
            os.makedirs(LOG_DIR, exist_ok=True)
            log = open(self.log_path, "a", encoding="utf-8", errors="replace")
            log.write(f"\n===== {time.strftime('%F %T')} 启动: {cmd} (cwd: {cwd}) =====\n")
            log.flush()
            self.proc = subprocess.Popen(
                cmd, cwd=cwd, shell=True, stdout=log, stderr=subprocess.STDOUT,
                env=localized_env())
        if wait_s:
            self.wait_ready(wait_s)

    def stop(self):
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=15)
                except Exception:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                                   capture_output=True)
            self.proc = None
        # 兜底：按端口清进程（引擎可能不是本进程拉起的）
        port = self.conf["health"].split(":")[2].split("/")[0]
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetTCPConnection -LocalPort %s -State Listen -ErrorAction SilentlyContinue | "
             "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }" % port],
            capture_output=True)

    def wait_ready(self, timeout_s: int = 1800) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.proc is not None and self.proc.poll() is not None:
                return False  # 进程退出了
            if self.healthy():
                return True
            time.sleep(4)
        return False

    def log_tail(self, n: int = 40) -> str:
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-n:])
        except OSError:
            return ""


class EngineManager:
    def __init__(self):
        cfg = _load_cfg()
        self.engines = {name: Engine(name, conf)
                        for name, conf in cfg["engines"].items()}

    def get(self, name: str) -> Engine:
        return self.engines[name]

    def ensure(self, name: str, timeout_s: int = 1800) -> bool:
        eng = self.get(name)
        if eng.healthy():
            return True
        eng.start()
        return eng.wait_ready(timeout_s)

    def status_all(self) -> dict:
        return {name: eng.status() for name, eng in self.engines.items()}


MANAGER = EngineManager()
