@echo off
chcp 65001 >nul
title 项目一 · 专属声音工作台

cd /d "%~dp0"

rem ---------- 如果工作台已经在运行：直接打开页面 ----------
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 9610 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo 工作台已在运行，直接打开页面 http://127.0.0.1:9610
    start http://127.0.0.1:9610
    timeout /t 3 >nul
    exit /b 0
)

rem ---------- 清理上次没退干净的残留（占用 9610 端口的进程）----------
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 9610 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }" >nul 2>&1

echo ============================================================
echo  项目一 · 专属声音工作台（GPT-SoVITS）
echo  页面: http://127.0.0.1:9610 （就绪后浏览器自动打开）
echo.
echo  ① 把激情解说录音放进 训练素材\ → 页面「开始训练」→ 用你的声音朗读
echo  ② 未训练时自动用默认参考音色零样本克隆，可直接朗读
echo.
echo  [说明]
echo  - 工作台几秒内就绪；语音引擎在点「朗读」时自动启动（首次约 1~2 分钟）
echo  - 生成解说词需要 DeepSeek Key：填在 config.yaml 的 deepseek.api_key
echo  - 停止工作台：关闭本窗口，或双击 关闭.bat
echo ============================================================
echo.

set /a RETRIES=0

:loop
"GPT-SoVITS\.venv\Scripts\python.exe" -u server.py

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
