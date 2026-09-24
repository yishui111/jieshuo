@echo off
chcp 65001 >nul
title 解说 TTS 服务启动器
cd /d "%~dp0"
call "index-tts\启动_TTS服务.bat"
