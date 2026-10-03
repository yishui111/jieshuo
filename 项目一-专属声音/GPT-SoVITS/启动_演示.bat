@echo off
chcp 65001 >nul
title GPT-SoVITS - 运行激情解说演示

:: 切换到本脚本所在目录
cd /d "%~dp0"

echo ============================================
echo  正在运行 GPT-SoVITS 激情解说演示...
echo  注意：需先启动 API 服务（启动_API.bat）
echo  输出目录：演示音频\GPT-SoVITS（或项目内 output\）
echo ============================================
.venv\Scripts\python.exe demo_jieshuo.py
pause
