@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u api_server.py -a 127.0.0.1 -p 9885 -c GPT_SoVITS/configs/tts_infer.yaml > _server_test.log 2>&1
