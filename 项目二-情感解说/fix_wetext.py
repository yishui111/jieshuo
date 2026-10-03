# -*- coding: utf-8 -*-
"""wetext 修复补丁：解决 IndexTTS-2.5 在 Windows 中文路径下无法启动的问题。

问题：wetext 包在导入时用 kaldifst 加载 FST，而 kaldifst 打不开含中文的路径
（项目路径带中文时引擎加载必失败）；部分 pip 源的 wetext 包数据还不完整
（缺 zh/ja FST），且缺少 contractions 依赖。

本脚本（可重复执行）：
  1. 安装缺失依赖 contractions
  2. 强制重装 wetext（补全包数据）
  3. 给 wetext/constants.py 打补丁：加载 FST 前把文件复制到 ASCII 临时路径

用法：双击本项目根目录的 修复wetext.bat，或
    index-tts\\.venv\\Scripts\\python.exe fix_wetext.py
"""

import io
import os
import subprocess
import sys

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.normpath(os.path.join(WORK_DIR, "index-tts", ".venv", "Scripts", "python.exe"))
CONSTANTS = os.path.normpath(os.path.join(
    WORK_DIR, "index-tts", ".venv", "Lib", "site-packages", "wetext", "constants.py"))

HELPER = '''

# --- 本地补丁：kaldifst 在 Windows 上无法打开含中文的路径，先把 FST 拷到 ASCII 临时路径再加载 ---
def _ascii_fst_path(fst_path):
    import os as _os
    import shutil as _shutil
    import tempfile as _tempfile
    src = files("wetext.fsts").joinpath(fst_path)
    src = str(src)
    try:
        src.encode("ascii")
        return src
    except UnicodeEncodeError:
        pass
    tmp_root = _os.path.join(_tempfile.gettempdir(), "wetext_fsts_ascii")
    _os.makedirs(tmp_root, exist_ok=True)
    dst = _os.path.join(tmp_root, fst_path.replace("/", "_").replace("\\\\", "_"))
    if not _os.path.isfile(dst) or _os.path.getsize(dst) != _os.path.getsize(src):
        _shutil.copyfile(src, dst)
    return dst
'''


def main():
    if not os.path.isfile(VENV_PY):
        print(f"[错误] 找不到虚拟环境解释器：{VENV_PY}")
        sys.exit(1)

    print(">> 安装依赖 contractions ...")
    subprocess.run([VENV_PY, "-m", "pip", "install", "-q", "-i",
                    "https://mirrors.aliyun.com/pypi/simple/", "contractions"], check=False)

    print(">> 强制重装 wetext（补全包数据）...")
    subprocess.run([VENV_PY, "-m", "pip", "install", "--force-reinstall", "--no-deps", "-q",
                    "-i", "https://mirrors.aliyun.com/pypi/simple/", "wetext"], check=False)

    if not os.path.isfile(CONSTANTS):
        print(f"[错误] 找不到 {CONSTANTS}，请先安装 wetext")
        sys.exit(1)

    src = io.open(CONSTANTS, encoding="utf-8").read()
    if "_ascii_fst_path" in src:
        print(">> 补丁已存在，跳过修改")
    else:
        print(">> 给 constants.py 打中文路径补丁 ...")
        old1 = '''    fst_path = files("wetext.fsts").joinpath(fst_path)
    return normalizer(str(fst_path))'''
        new1 = '''    return normalizer(_ascii_fst_path(fst_path))'''
        old2 = '''    return str(files("wetext.fsts").joinpath(fst_path))'''
        new2 = '''    return _ascii_fst_path(fst_path)'''
        assert old1 in src and old2 in src, "wetext 版本不匹配，补丁不适用"
        src = src.replace(old1, new1).replace(old2, new2)
        idx = src.index("def load_fst")
        src = src[:idx] + HELPER.strip() + "\n\n\n" + src[idx:]
        io.open(CONSTANTS, "w", encoding="utf-8").write(src)

    print(">> 验证 ...")
    r = subprocess.run([VENV_PY, "-c",
                        "from wetext import Normalizer; "
                        "n = Normalizer(remove_erhua=False, lang='zh', operator='tn'); "
                        "print('WETEXT_OK:', n.normalize('测试三比二，进球了！'))"],
                       capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip()[-200:])
    if "WETEXT_OK" in out:
        print(">> wetext 修复完成")
    else:
        print(">> 验证未通过，请把上面的输出发给维护者")
        sys.exit(1)


if __name__ == "__main__":
    main()
