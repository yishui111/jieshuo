# -*- coding: utf-8 -*-
"""引擎管理：按需启动/停止本项目语音引擎，供工作台调用。

引擎与端口（定义在本项目 config.yaml）：
  gpt_sovits  GPT-SoVITS 专属声音引擎（训练+推理）  -> http://127.0.0.1:9885

要点：
  - 启动前如果端口被占：先清掉占用端口的旧进程（那是上次没退干净的引擎）
  - 引擎首次加载模型需要几分钟，wait_ready() 轮询健康检查直到就绪
  - 所有子进程日志写入 本项目/logs/engine_<名字>.log，页面可查看
"""

import os
import subprocess
import threading
import time

import requests

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(WORK_DIR, "logs")


def load_config() -> dict:
    import yaml
    with open(os.path.join(WORK_DIR, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def localized_env() -> dict:
    """子进程环境：把 HF / ModelScope 的模型缓存固定到项目内（不占 C 盘）。"""
    cfg = load_config()
    cache = os.path.normpath(os.path.join(WORK_DIR, cfg["paths"]["model_cache_dir"]))
    env = os.environ.copy()
    env["HF_HOME"] = os.path.join(cache, "huggingface")
    env["MODELSCOPE_CACHE"] = os.path.join(cache, "modelscope")
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    return env


def _free_port(port: int):
    """杀掉占用端口的进程（引擎端口专用；上次异常退出会留下僵尸进程）。"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction SilentlyContinue | "
         "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }" % port],
        capture_output=True)


class Engine:
    """一个语音引擎 = 一条启动命令 + 一个健康检查地址。"""

    def __init__(self, name: str, conf: dict):
        self.name = name
        self.conf = conf
        self.proc = None
        self.log_path = os.path.join(LOG_DIR, f"engine_{name}.log")
        self.lock = threading.Lock()
        self.port = int(conf["health"].split(":")[2].split("/")[0])

    # ---- 状态 ----
    def healthy(self) -> bool:
        try:
            # 超时给短一些：/api/status 每次会探测两个引擎，不能拖慢页面
            r = requests.get(self.conf["health"], timeout=2)
            if not r.ok:
                return False
            field = self.conf.get("ready_field")
            data = r.json()
            return bool(data.get(field, True)) if field else True
        except Exception:
            return False

    def status(self) -> str:
        """stopped / starting / ready"""
        if self.healthy():
            return "ready"
        if self.proc is not None and self.proc.poll() is None:
            return "starting"
        return "stopped"

    # ---- 启停 ----
    def start(self):
        with self.lock:
            if self.healthy():
                return
            _free_port(self.port)
            cwd = os.path.normpath(os.path.join(WORK_DIR, self.conf["cwd"]))
            # cmd.exe 无法执行 ../ 开头、含正斜杠的相对路径：先把可执行文件解析成绝对路径
            exe_and_args = self.conf["cmd"].split(" ", 1)
            exe = os.path.normpath(os.path.join(cwd, exe_and_args[0]))
            cmd = f'"{exe}" {exe_and_args[1]}' if len(exe_and_args) > 1 else f'"{exe}"'
            os.makedirs(LOG_DIR, exist_ok=True)
            log = open(self.log_path, "a", encoding="utf-8", errors="replace")
            log.write(f"\n===== {time.strftime('%F %T')} 启动 =====\n{cmd}\n(cwd: {cwd})\n")
            log.flush()
            self.proc = subprocess.Popen(cmd, cwd=cwd, shell=True,
                                         stdout=log, stderr=subprocess.STDOUT,
                                         env=localized_env())

    def stop(self):
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=15)
                except Exception:
                    pass
            self.proc = None
        _free_port(self.port)

    def wait_ready(self, timeout_s: float, progress=None) -> bool:
        """轮询直到就绪。progress(stage_text) 用于向页面汇报阶段。"""
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.healthy():
                return True
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(
                    f"引擎进程意外退出（已运行 {time.time()-t0:.0f} 秒），"
                    f"详情见 工作台/logs/engine_{self.name}.log")
            if progress:
                progress(f"加载模型中… 已等 {time.time()-t0:.0f} 秒（首次启动较慢，属正常）")
            time.sleep(4)
        raise RuntimeError(f"引擎 {timeout_s:.0f} 秒内未就绪，请查看 工作台/logs/engine_{self.name}.log")

    def log_tail(self, n: int = 40) -> str:
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-n:])
        except OSError:
            return ""


class EngineManager:
    def __init__(self):
        self.engines = {name: Engine(name, conf)
                        for name, conf in load_config()["engines"].items()}

    def get(self, name: str) -> Engine:
        return self.engines[name]

    def ensure(self, name: str, timeout_s: float, progress=None) -> None:
        """确保引擎就绪；不就绪就启动并等待（可能几分钟），失败抛异常。

        本机偶发"加载中进程无声退出"（CUDA/资源浪潮），自动重试最多 3 次。
        """
        eng = self.get(name)
        if eng.healthy():
            return
        last_err = None
        for attempt in (1, 2, 3):
            try:
                if progress:
                    progress(f"第 {attempt}/3 次尝试启动")
                eng.start()
                eng.wait_ready(timeout_s, progress)
                return
            except Exception as e:
                last_err = e
                if progress:
                    progress(f"第 {attempt} 次启动失败：{e}")
                time.sleep(10)
        raise RuntimeError(f"引擎连续 3 次启动失败：{last_err}")

    def status_all(self) -> dict:
        return {name: eng.status() for name, eng in self.engines.items()}


MANAGER = EngineManager()
