@echo off
chcp 65001 >nul
title GPT-SoVITS 推理 WebUI (9872)

:: 切换到本脚本所在目录
cd /d "%~dp0"

set PYTHONPATH=%CD%

echo ============================================
echo  GPT-SoVITS 推理 WebUI  -^>  http://127.0.0.1:9872
echo  关闭本窗口即停止服务
echo ============================================
.venv\Scripts\python.exe GPT_SoVITS/inference_webui.py zh
pause
