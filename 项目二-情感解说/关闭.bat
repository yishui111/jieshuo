@echo off
chcp 65001 >nul
title 关闭 项目二 · 情感解说工作台
cd /d "%~dp0"

echo ============================================
echo  正在关闭 项目二（工作台 9620 / IndexTTS 引擎 9602）
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ids=@(); foreach ($p in 9620,9602) { $ids += @(Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess }) }; $ids += @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match '项目二-情感解说' } | ForEach-Object { $_.ProcessId }); $ids = @($ids | Where-Object { $_ } | Sort-Object -Unique); if ($ids.Count -eq 0) { Write-Host '  没有发现正在运行的项目二服务' } else { foreach ($i in $ids) { Write-Host ('  结束 PID ' + $i); Stop-Process -Id $i -Force -ErrorAction SilentlyContinue } }"

echo.
echo 完成。启动窗口若还开着，直接关掉即可。
pause
