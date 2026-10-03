@echo off
chcp 65001 >nul
title 修复 wetext（IndexTTS 中文路径问题）
cd /d "%~dp0"
echo 正在修复 wetext（安装缺失依赖 + 补全包数据 + 中文路径补丁）...
"index-tts\.venv\Scripts\python.exe" fix_wetext.py
pause
