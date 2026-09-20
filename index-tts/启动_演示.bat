@echo off
chcp 65001 >nul
title IndexTTS-2 - 运行激情解说演示

:: 切换到本脚本所在目录
cd /d "%~dp0"

echo ============================================
echo  正在运行 IndexTTS-2 激情解说演示...
echo  输出目录：演示音频\IndexTTS-2（或项目内 output\）
echo.
echo  [耗时说明]
echo  首次运行（或重启电脑后第一次）需要 5~15 分钟：
echo  要读取 4.4GB 模型，而本盘读取速度约 25MB/s。
echo  期间黑框可能长时间没有输出，这是正常的，请勿关闭。
echo  第二次之后运行会快很多（系统缓存命中）。
echo ============================================
echo.

.venv\Scripts\python.exe -u demo_jieshuo.py

echo.
echo ============================================
echo  演示运行结束。
echo ============================================
pause
