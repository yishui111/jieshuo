@echo off
chcp 65001 >nul
title GPT-SoVITS API + 引导式控制台 (9885)

:: 切换到本脚本所在目录
cd /d "%~dp0"

echo ============================================
echo  GPT-SoVITS 引导式控制台  -^>  http://127.0.0.1:9885
echo  服务就绪后会自动打开浏览器（首次加载模型约 1~2 分钟）
echo  机器接口文档: http://127.0.0.1:9885/docs
echo  关闭本窗口即停止服务
echo ============================================
.venv\Scripts\python.exe api_server.py -a 127.0.0.1 -p 9885 -c GPT_SoVITS/configs/tts_infer.yaml
pause
