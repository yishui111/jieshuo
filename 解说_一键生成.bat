@echo off
chcp 65001 >nul
title 激情解说一键生成

cd /d "%~dp0"

echo ============================================
echo  激情解说一键生成
echo  输入主题文字（或拖入视频） -^> 解说词 -^> 激情音频
echo.
echo  [前置条件]
echo  1. 解说 TTS 服务已启动（index-tts\启动_TTS服务.bat）
echo  2. 只生成解说词不合成音频：加参数 --no-tts
echo ============================================
echo.

:: 用 index-tts 的虚拟环境跑流水线（里面有 soundfile/yaml 等依赖）
"index-tts\.venv\Scripts\python.exe" -u pipeline\jieshuo.py %*

echo.
pause
