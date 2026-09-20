@echo off
chcp 936 >nul
title CosyVoice2 - 关闭 WebUI (9600)
cd /d "%~dp0"

echo ============================================
echo  正在关闭 CosyVoice2 WebUI（端口 9600）
echo ============================================
echo.

setlocal enabledelayedexpansion
set FOUND=0
set DONEPID=

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9600 " ^| findstr "LISTENING"') do (
    if not "!DONEPID!"=="%%a" (
        echo   发现监听进程 PID=%%a，正在结束...
        taskkill /F /PID %%a >nul 2>&1
        set DONEPID=%%a
        set FOUND=1
    )
)

if "!FOUND!"=="0" echo   端口 9600 上没有正在运行的服务（可能已经关了）。
if "!FOUND!"=="1" echo   已停止。
endlocal
echo.

netstat -ano | findstr ":9600 " | findstr "LISTENING" >nul
if errorlevel 1 echo   端口 9600 已释放，可以安全重启。
if not errorlevel 1 echo   警告：端口 9600 仍被占用，请手动检查。

echo.
echo 按任意键关闭本窗口。
pause >nul
