@echo off
chcp 65001 >nul
title 关闭 IndexTTS-2 WebUI
cd /d "%~dp0"

echo ============================================
echo  正在关闭 IndexTTS-2 WebUI（端口 9601）
echo ============================================
echo.

setlocal enabledelayedexpansion
set KILLED=0

:: 1) 按监听端口查找并结束进程（服务已就绪的情况）
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9601" ^| findstr "LISTENING"') do (
    echo [端口 9601] 结束进程 PID=%%a
    taskkill /F /PID %%a >nul 2>&1
    if not errorlevel 1 set KILLED=1
)

:: 2) 兜底：仍在加载模型、尚未监听端口的 python 进程
for /f "tokens=2 delims==" %%a in ('wmic process where "name='python.exe' and commandline like '%%webui.py%%'" get processid /value 2^>nul ^| findstr "="') do (
    echo [加载中]   结束进程 PID=%%a
    taskkill /F /PID %%a >nul 2>&1
    if not errorlevel 1 set KILLED=1
)

echo.
if "!KILLED!"=="1" (
    echo 已关闭 IndexTTS-2 WebUI，端口 9601 已释放。
) else (
    echo 未发现正在运行的服务（端口 9601 空闲）。
)
echo.
pause
