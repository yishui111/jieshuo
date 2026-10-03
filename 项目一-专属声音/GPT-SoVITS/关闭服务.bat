@echo off
chcp 936 >nul
title 关闭 GPT-SoVITS 服务
cd /d "%~dp0"

echo ============================================
echo  正在关闭 GPT-SoVITS 服务（WebUI 9872 / API 9885）
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ids=@(); foreach ($p in 9885,9872) { $ids += @(Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess }) }; $ids += @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'api_server\.py|inference_webui\.py' } | ForEach-Object { $_.ProcessId }); $ids = @($ids | Where-Object { $_ } | Sort-Object -Unique); if ($ids.Count -eq 0) { Write-Host '  没有发现正在运行的 GPT-SoVITS 服务' } else { foreach ($i in $ids) { Write-Host ('  结束 PID ' + $i); Stop-Process -Id $i -Force -ErrorAction SilentlyContinue } }"

echo.
echo 完成。原来那个黑框窗口若停在“请按任意键继续”，直接关掉即可。
pause
