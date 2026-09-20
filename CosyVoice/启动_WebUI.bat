@echo off
chcp 65001 >nul
title CosyVoice2 - 激情解说 TTS (WebUI: 9600)

:: 切换到本脚本所在目录（支持从任意位置启动）
cd /d "%~dp0"

echo ============================================
echo  CosyVoice2 WebUI  -^>  http://127.0.0.1:9600
echo  关闭本窗口即停止服务
echo ============================================
echo.
echo [1/3] 正在启动 Python 并加载依赖库（torch/gradio 等）...
echo       项目在 G 盘（机械硬盘，读速约 40MB/s），冷启动约 4~6 分钟，期间无输出属正常，请勿关闭窗口！
echo       服务就绪后会自动弹出浏览器；若没弹，手动打开 http://127.0.0.1:9600 即可。
echo       停止服务：双击「关闭_WebUI.bat」，或直接关掉本窗口。
echo.
.venv\Scripts\python.exe -u webui.py --port 9600 --model_dir pretrained_models/CosyVoice2-0.5B
echo.
echo 进程已退出（若上方有红色报错，请把报错信息发给助手）。
pause
