@echo off
chcp 65001 >nul
title 激情解说 · 统一工作台

cd /d "%~dp0"

echo ============================================
echo  激情解说 · 统一工作台
echo  浏览器将自动打开 http://127.0.0.1:9610
echo.
echo  项目一 · 专属声音：训练素材\ 放录音 → 页面一键训练 → 用你的声音朗读
echo  项目二 · 情感解说：故事 → DeepSeek 解说词 → IndexTTS-2.5 激情洋溢朗读
echo.
echo  [说明]
echo  - 语音引擎会在首次合成时自动启动（首次要加载模型，耐心等）
echo  - 机器高内存负载时服务可能被系统压退出，本窗口会自动重启工作台
echo  - 停止工作台：关闭本窗口
echo ============================================
echo.

set /a RETRIES=0

:loop
"index-tts\.venv\Scripts\python.exe" -u 工作台\server.py

set /a RETRIES+=1
if %RETRIES% GEQ 50 (
    echo [错误] 工作台反复退出，已达自动重启上限。
    pause
    exit /b 1
)
echo.
echo [警告] 工作台退出（代码 %errorlevel%），5 秒后自动重启（第 %RETRIES% 次）……
timeout /t 5 /nobreak >nul
goto loop
