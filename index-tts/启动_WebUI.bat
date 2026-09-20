@echo off
chcp 65001 >nul
title IndexTTS-2 - 激情解说 TTS (WebUI: 9601)

:: 切换到本脚本所在目录
cd /d "%~dp0"

echo ============================================
echo  IndexTTS-2 WebUI  -^>  http://127.0.0.1:9601
echo.
echo  [启动耗时说明]
echo  首次启动（或重启电脑后第一次）需要 5~15 分钟：
echo  要读取 4.4GB 模型和依赖库，而本盘读取速度约 25MB/s。
echo  期间黑框可能长时间没有输出，这是正常的，请勿关闭。
echo  第二次之后启动会快很多（系统缓存命中）。
echo.
echo  [操作]
echo  - 服务就绪后会自动打开浏览器（无需手动输入网址）
echo  - 停止服务：关掉本窗口，或双击「关闭_WebUI.bat」
echo ============================================
echo.

.venv\Scripts\python.exe -u webui.py --version 2 --model_dir checkpoints/IndexTTS-2 --port 9601

echo.
echo ============================================
echo  服务已停止。
echo ============================================
pause
