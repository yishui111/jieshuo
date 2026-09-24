@echo off
chcp 65001 >nul
title 解说 TTS 服务 (IndexTTS-2.5, 端口 9602)

:: 切换到本脚本所在目录
cd /d "%~dp0"

echo ============================================
echo  解说 TTS 服务 (IndexTTS-2.5)  ->  http://127.0.0.1:9602
echo.
echo  [说明]
echo  - 这是解说流水线的语音合成后端，先启动它，再运行一键解说
echo  - 首次启动要把约 5GB 模型读进显存，黑框长时间无输出属正常
echo  - 就绪标志：出现 "Uvicorn running on http://127.0.0.1:9602"
echo  - 停止服务：双击「关闭_TTS服务.bat」（不要直接关窗口，否则不会清理停止标记）
echo  - 服务意外退出时会自动重启（最多 100 次）
echo ============================================
echo.

if exist "tts_server.stop" del /q "tts_server.stop"

if not exist "checkpoints\IndexTTS-2.5\config.yaml" (
    echo [错误] 未找到 checkpoints\IndexTTS-2.5 模型权重。
    echo        先按 README 下载 IndexTTS-2.5，或临时改用 2.0 权重：
    echo        .venv\Scripts\python.exe tts_server.py --version 2 --model_dir checkpoints/IndexTTS-2
    pause
    exit /b 1
)

set /a RETRIES=0

:loop
.venv\Scripts\python.exe -u tts_server.py --version 2.5 --model_dir checkpoints/IndexTTS-2.5 --port 9602

if exist "tts_server.stop" (
    del /q "tts_server.stop"
    echo.
    echo ============================================
    echo  已收到停止指令，服务关闭。
    echo ============================================
    pause
    exit /b 0
)

set /a RETRIES+=1
if %RETRIES% GEQ 100 (
    echo [错误] 服务反复退出，已达自动重启上限，请检查环境。
    pause
    exit /b 1
)

echo.
echo [警告] 服务异常退出（代码 %errorlevel%），10 秒后自动重启（第 %RETRIES% 次）……
timeout /t 10 /nobreak >nul
goto loop
