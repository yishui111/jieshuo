@echo off
chcp 65001 >nul
title CosyVoice2 - 运行激情解说演示

:: 切换到本脚本所在目录
cd /d "%~dp0"

echo ============================================
echo  正在运行 CosyVoice2 激情解说演示...
echo  输出目录：演示音频\CosyVoice2（或项目内 output\）
echo ============================================
echo.
echo 项目在 G 盘（机械硬盘），加载依赖和模型约 4~6 分钟，期间无输出属正常，请勿关闭窗口！
echo.
.venv\Scripts\python.exe -u demo_jieshuo.py
echo.
echo 进程已退出（若上方有红色报错，请把报错信息发给助手）。
pause
