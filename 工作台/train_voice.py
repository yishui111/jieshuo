# -*- coding: utf-8 -*-
"""项目一 · 专属声音训练编排：把 训练素材/ 里的录音训练成 GPT-SoVITS 专属声音。

流程（全自动，逐条日志写入 工作台/logs/train_<exp>.log）：
  1. 检查素材        训练素材/ 下的 wav/mp3/flac/m4a
  2. 切片            静音检测切成 4~15s 小段（tools/slice_audio.py）
  3. ASR 标注        Fun-ASR-Nano 生成 文本标注 .list（tools/asr/funasr_asr.py）
  4. 数据集预处理    1-get-text / 2-get-hubert-wav32k / 3-get-semantic（"一键三连"）
  5. SoVITS 微调     GPT_SoVITS/s2_train.py（v2 底模 + 判别器）
  6. GPT 微调        GPT_SoVITS/s1_train.py（v2 底模）
  7. 挑参考音频      自动选一条 10~30 字的切片作推理参考，写入 voice_config.json

训练产物：GPT-SoVITS/SoVITS_weights_v2/ 、GPT-SoVITS/GPT_weights_v2/ 下以 exp 名命名的权重。
所有 HF/ModelScope 缓存钉在 工作台/model_cache/，不占 C 盘。
"""

import glob
import json
import os
import subprocess
import sys
import threading
import time
import traceback

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
GSV_ROOT = os.path.normpath(os.path.join(WORK_DIR, "..", "GPT-SoVITS"))
GSV_PY = os.path.join(GSV_ROOT, ".venv", "Scripts", "python.exe")

S2_PRETRAINED_G = os.path.join(GSV_ROOT, "GPT_SoVITS", "pretrained_models",
                               "gsv-v2final-pretrained", "s2G2333k.pth")
S2_PRETRAINED_D = os.path.join(GSV_ROOT, "GPT_SoVITS", "pretrained_models",
                               "gsv-v2final-pretrained", "s2D2333k.pth")
S1_PRETRAINED = os.path.join(GSV_ROOT, "GPT_SoVITS", "pretrained_models",
                             "gsv-v2final-pretrained", "s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt")
BERT_DIR = os.path.join(GSV_ROOT, "GPT_SoVITS", "pretrained_models", "chinese-roberta-wwm-ext-large")
HUBERT_DIR = os.path.join(GSV_ROOT, "GPT_SoVITS", "pretrained_models", "chinese-hubert-base")

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}

_state = {"running": False, "step": "", "error": "", "log_file": "",
          "exp_name": "", "started_at": "", "finished_at": "", "result": {}}
_lock = threading.Lock()


def state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["running"]


def list_materials() -> dict:
    import yaml
    with open(os.path.join(WORK_DIR, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    mat_dir = os.path.normpath(os.path.join(WORK_DIR, cfg["paths"]["materials_dir"]))
    files = []
    total = 0.0
    if os.path.isdir(mat_dir):
        for fp in sorted(glob.glob(os.path.join(mat_dir, "*"))):
            if os.path.splitext(fp)[1].lower() not in AUDIO_EXTS:
                continue
            dur = _audio_duration(fp)
            total += dur
            files.append({"file": os.path.basename(fp), "seconds": round(dur, 1),
                          "size_mb": round(os.path.getsize(fp) / 1048576, 1)})
    return {"dir": mat_dir, "count": len(files), "total_seconds": round(total, 1), "files": files}


def _audio_duration(path: str) -> float:
    try:
        import soundfile as sf
        info = sf.info(path)
        return info.duration
    except Exception:
        return 0.0


def _log(logf, msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    logf.write(line + "\n")
    logf.flush()


def _run_cmd(logf, cmd: str, cwd: str, env: dict, step: str, timeout_s: int = 6 * 3600):
    _log(logf, f"$ {cmd}")
    p = subprocess.run(cmd, cwd=cwd, env=env, shell=True,
                       stdout=logf, stderr=subprocess.STDOUT, timeout=timeout_s)
    if p.returncode != 0:
        raise RuntimeError(f"{step} 失败（退出码 {p.returncode}），日志见上方")
    _log(logf, f"{step} 完成")


def _env_base(model_cache: str) -> dict:
    env = os.environ.copy()
    env["HF_HOME"] = os.path.join(model_cache, "huggingface")
    env["MODELSCOPE_CACHE"] = os.path.join(model_cache, "modelscope")
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    env["PYTHONPATH"] = os.pathsep.join([
        GSV_ROOT,                    # tools.*（切片/ASR 脚本用）
        os.path.join(GSV_ROOT, "GPT_SoVITS"),  # text.cleaner 等训练脚本用
    ])
    return env


def _latest_file(folder: str, prefix: str) -> str:
    cands = [f for f in glob.glob(os.path.join(folder, prefix + "*"))
             if os.path.isfile(f)]
    if not cands:
        return ""
    return max(cands, key=os.path.getmtime)


def run_training(exp_name: str, sovits_epochs: int, gpt_epochs: int,
                 sovits_bs: int, gpt_bs: int, save_every: int):
    """阻塞式全流程训练（由 server 起线程调用）。"""
    with _lock:
        if _state["running"]:
            raise RuntimeError("已有训练在进行中")
        _state.update(running=True, step="准备", error="", result={}, exp_name=exp_name,
                      started_at=time.strftime("%F %T"), finished_at="")

    import yaml
    with open(os.path.join(WORK_DIR, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    mat_dir = os.path.normpath(os.path.join(WORK_DIR, cfg["paths"]["materials_dir"]))
    model_cache = os.path.normpath(os.path.join(WORK_DIR, cfg["paths"]["model_cache_dir"]))
    log_path = os.path.join(WORK_DIR, "logs", f"train_{exp_name}.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    _state["log_file"] = log_path

    exp_name = "".join(c for c in exp_name.strip() if c not in '\\/:*?"<>| ').strip() or "我的解说声音"
    workdir = os.path.join(WORK_DIR, "训练数据", exp_name)
    sliced_dir = os.path.join(workdir, "sliced")
    asr_dir = os.path.join(workdir, "asr")
    opt_dir = os.path.join(GSV_ROOT, "logs", exp_name)
    env = _env_base(model_cache)

    try:
        with open(log_path, "a", encoding="utf-8") as logf:
            t0 = time.time()
            _log(logf, f"===== 开始训练专属声音：{exp_name} =====")

            # 1) 素材检查
            _state["step"] = "检查素材"
            materials = [f for f in glob.glob(os.path.join(mat_dir, "*"))
                         if os.path.splitext(f)[1].lower() in AUDIO_EXTS]
            if not materials:
                raise RuntimeError(f"训练素材为空：请先把录音放进 {mat_dir}")
            total = sum(_audio_duration(f) for f in materials)
            _log(logf, f"素材 {len(materials)} 个文件，共约 {total/60:.1f} 分钟")
            if total < 60:
                _log(logf, "提示：素材短于 1 分钟，效果可能有限；建议提供 3~30 分钟清晰录音")

            # 2) 切片
            _state["step"] = "切片"
            os.makedirs(sliced_dir, exist_ok=True)
            cmd = (f'"{GSV_PY}" -s tools/slice_audio.py "{mat_dir}" "{sliced_dir}"'
                   f' -34 4000 300 10 500 0.9 0.25 0 1')
            _run_cmd(logf, cmd, GSV_ROOT, env, "切片")
            n_slices = len(glob.glob(os.path.join(sliced_dir, "*.wav")))
            if n_slices == 0:
                raise RuntimeError("切片结果为空，请检查录音是否有效")
            _log(logf, f"切片完成：{n_slices} 段")

            # 3) ASR 标注（已有标注则跳过）
            _state["step"] = "ASR标注"
            os.makedirs(asr_dir, exist_ok=True)
            existing = sorted(glob.glob(os.path.join(asr_dir, "*.list")),
                              key=os.path.getmtime, reverse=True)
            if existing:
                inp_text = existing[0]
                n_have = len([l for l in open(inp_text, encoding="utf-8").read().splitlines() if l.strip()])
                _log(logf, f"已有标注文件，跳过 ASR：{inp_text}（{n_have} 条）")
            else:
                # ASR 固定走 CPU：GPU 上新起进程做 CUDA 初始化在本机偶发无声崩溃，CPU 稳定且耗时可接受
                asr_env = env.copy()
                asr_env["CUDA_VISIBLE_DEVICES"] = ""
                cmd = f'"{GSV_PY}" -s tools/asr/funasr_asr.py -i "{sliced_dir}" -o "{asr_dir}" -s large -l zh -p float32'
                _run_cmd(logf, cmd, GSV_ROOT, asr_env, "ASR标注", timeout_s=4 * 3600)
                lists = glob.glob(os.path.join(asr_dir, "*.list"))
                if not lists:
                    raise RuntimeError("ASR 未产出标注文件")
                inp_text = lists[0]
            n_lines = len([l for l in open(inp_text, encoding="utf-8").read().splitlines() if l.strip()])
            if n_lines == 0:
                raise RuntimeError("ASR 没有产出有效标注，请检查录音质量和清晰度")
            if n_lines < 20:
                _log(logf, f"提示：有效标注仅 {n_lines} 条，素材越多训练效果越好（建议几十条以上）")
            _log(logf, f"ASR 完成：{n_lines} 条标注 -> {inp_text}")

            # 4) 数据集预处理（一键三连；已有产物自动跳过，便于中断续跑）
            _state["step"] = "数据集预处理"
            os.makedirs(opt_dir, exist_ok=True)
            common = {
                "inp_text": inp_text, "inp_wav_dir": "", "exp_name": exp_name,
                "opt_dir": opt_dir, "bert_pretrained_dir": BERT_DIR,
                "cnhubert_base_dir": HUBERT_DIR, "is_half": "True",
                "pretrained_s2G": S2_PRETRAINED_G,
                "s2config_path": os.path.join(GSV_ROOT, "GPT_SoVITS", "configs", "s2.json"),
                "i_part": "0", "all_parts": "1", "_CUDA_VISIBLE_DEVICES": "0",
            }
            steps = [
                ("1A-文本", "GPT_SoVITS/prepare_datasets/1-get-text.py",
                 os.path.join(opt_dir, "2-name2text.txt")),
                ("1B-特征", "GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py",
                 os.path.join(opt_dir, "4-wav32k.pth")),
                ("1C-语义", "GPT_SoVITS/prepare_datasets/3-get-semantic.py",
                 os.path.join(opt_dir, "6-name2semantic.tsv")),
            ]
            for step_name, script, product in steps:
                if os.path.isfile(product) and os.path.getsize(product) > 0:
                    _log(logf, f"{step_name} 产物已存在，跳过：{product}")
                    continue
                run_env = env.copy()
                run_env.update(common)
                _run_cmd(logf, f'"{GSV_PY}" -s {script}', GSV_ROOT, run_env, step_name,
                         timeout_s=4 * 3600)
            # 合并分片输出（1A 与 1C 都按分片写文件）
            for part_name, full_name in [("2-name2text-0.txt", "2-name2text.txt"),
                                         ("6-name2semantic-0.tsv", "6-name2semantic.tsv")]:
                part = os.path.join(opt_dir, part_name)
                if os.path.isfile(part):
                    os.replace(part, os.path.join(opt_dir, full_name))

            # 5) SoVITS (s2) 微调
            _state["step"] = "SoVITS微调"
            os.makedirs(os.path.join(opt_dir, "logs_s2_v2"), exist_ok=True)  # s2_train 会往里拷底模
            os.makedirs(os.path.join(GSV_ROOT, "SoVITS_weights_v2"), exist_ok=True)  # 权重保存目录
            os.makedirs(os.path.join(GSV_ROOT, "GPT_weights_v2"), exist_ok=True)
            with open(os.path.join(GSV_ROOT, "GPT_SoVITS", "configs", "s2.json"),
                      encoding="utf-8") as f:
                s2cfg = json.load(f)
            s2cfg["train"].update({
                "batch_size": sovits_bs, "epochs": sovits_epochs, "text_low_lr_rate": 0.4,
                "pretrained_s2G": S2_PRETRAINED_G, "pretrained_s2D": S2_PRETRAINED_D,
                "if_save_latest": True, "if_save_every_weights": True,
                "save_every_epoch": save_every, "gpu_numbers": "0",
                "grad_ckpt": False, "lora_rank": 32,
            })
            s2cfg["model"]["version"] = "v2"
            s2cfg["data"]["exp_dir"] = s2cfg["s2_ckpt_dir"] = opt_dir
            s2cfg["save_weight_dir"] = "SoVITS_weights_v2"
            s2cfg["name"] = exp_name
            s2cfg["version"] = "v2"
            tmp_s2 = os.path.join(opt_dir, "tmp_s2.json")
            with open(tmp_s2, "w", encoding="utf-8") as f:
                json.dump(s2cfg, f)
            _run_cmd(logf, f'"{GSV_PY}" -s GPT_SoVITS/s2_train.py --config "{tmp_s2}"',
                     GSV_ROOT, env, "SoVITS微调", timeout_s=24 * 3600)

            # 6) GPT (s1) 微调
            _state["step"] = "GPT微调"
            os.makedirs(os.path.join(opt_dir, "logs_s1_v2"), exist_ok=True)
            import yaml as _yaml
            with open(os.path.join(GSV_ROOT, "GPT_SoVITS", "configs", "s1longer-v2.yaml"),
                      encoding="utf-8") as f:
                s1cfg = _yaml.safe_load(f)
            s1cfg["train"].update({
                "batch_size": gpt_bs, "epochs": gpt_epochs,
                "save_every_n_epoch": save_every, "if_save_every_weights": True,
                "if_save_latest": True, "if_dpo": False,
                "half_weights_save_dir": "GPT_weights_v2", "exp_name": exp_name,
            })
            s1cfg["pretrained_s1"] = S1_PRETRAINED
            s1cfg["train_semantic_path"] = os.path.join(opt_dir, "6-name2semantic.tsv")
            s1cfg["train_phoneme_path"] = os.path.join(opt_dir, "2-name2text.txt")
            s1cfg["output_dir"] = os.path.join(opt_dir, f"logs_s1_v2")
            tmp_s1 = os.path.join(opt_dir, "tmp_s1.yaml")
            with open(tmp_s1, "w", encoding="utf-8") as f:
                _yaml.dump(s1cfg, f, default_flow_style=False, allow_unicode=True)
            s1_env = env.copy()
            s1_env["_CUDA_VISIBLE_DEVICES"] = "0"
            s1_env["hz"] = "25hz"
            _run_cmd(logf, f'"{GSV_PY}" -s GPT_SoVITS/s1_train.py --config_file "{tmp_s1}"',
                     GSV_ROOT, s1_env, "GPT微调", timeout_s=24 * 3600)

            # 7) 挑参考音频 + 写 voice_config
            _state["step"] = "整理产物"
            sovits_w = _latest_file(os.path.join(GSV_ROOT, "SoVITS_weights_v2"), exp_name)
            gpt_w = _latest_file(os.path.join(GSV_ROOT, "GPT_weights_v2"), exp_name)
            if not sovits_w or not gpt_w:
                raise RuntimeError("训练完成但没找到权重文件")
            ref_audio, ref_text = "", ""
            text_list_path = os.path.join(opt_dir, "2-name2text.txt")
            for line in open(text_list_path, encoding="utf-8").read().splitlines():
                parts = line.split("|")
                if len(parts) >= 4:
                    wav_path, text = parts[0], parts[3].strip()
                    if os.path.isfile(wav_path) and 10 <= len(text) <= 30:
                        ref_audio, ref_text = wav_path, text
                        break
            if not ref_audio:
                ref_audio = n_slices and sorted(glob.glob(os.path.join(sliced_dir, "*.wav")))[0] or ""
            voice_cfg = {
                "exp_name": exp_name,
                "sovits_weights": sovits_w,
                "gpt_weights": gpt_w,
                "ref_audio": ref_audio,
                "prompt_text": ref_text,
                "trained_at": time.strftime("%F %T"),
                "materials_minutes": round(total / 60, 1),
            }
            with open(os.path.join(WORK_DIR, "voice_config.json"), "w", encoding="utf-8") as f:
                json.dump(voice_cfg, f, ensure_ascii=False, indent=2)
            _log(logf, f"训练完成，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            _log(logf, f"SoVITS 权重: {sovits_w}")
            _log(logf, f"GPT 权重: {gpt_w}")
            _log(logf, f"参考音频: {ref_audio}")
            _log(logf, f"参考文本: {ref_text}")
            _state["result"] = voice_cfg
    except Exception as e:
        _state["error"] = str(e)
        print(traceback.format_exc())
        try:
            with open(log_path, "a", encoding="utf-8") as logf:
                _log(logf, f"训练失败：{e}")
        except OSError:
            pass
    finally:
        _state["running"] = False
        _state["step"] = "已结束"
        _state["finished_at"] = time.strftime("%F %T")


def start_training(exp_name: str, sovits_epochs: int, gpt_epochs: int,
                   sovits_bs: int, gpt_bs: int, save_every: int) -> dict:
    if is_running():
        return {"ok": False, "msg": "已有训练在进行中"}
    if not os.path.isfile(GSV_PY):
        return {"ok": False, "msg": f"找不到 GPT-SoVITS 虚拟环境：{GSV_PY}"}
    threading.Thread(
        target=run_training,
        args=(exp_name, sovits_epochs, gpt_epochs, sovits_bs, gpt_bs, save_every),
        daemon=True).start()
    return {"ok": True, "msg": "训练已启动"}


if __name__ == "__main__":
    # 命令行自测：python train_voice.py
    print(json.dumps(list_materials(), ensure_ascii=False, indent=2))
    print(json.dumps(state(), ensure_ascii=False, indent=2))
