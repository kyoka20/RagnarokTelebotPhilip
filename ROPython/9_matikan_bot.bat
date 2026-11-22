@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Matikan bot sepenuhnya: penjaga (jaga_bot.ps1) tidak menyalakannya lagi.
rem Menyalakan lagi: buka 4_jalankan_bot.bat (file BOT_DIMATIKAN.txt otomatis terhapus).
> "BOT_DIMATIKAN.txt" echo Dimatikan manual %date% %time%
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID } | Where-Object { $_.CommandLine -like '*bot.py*' -or $_.CommandLine -like '*4_jalankan_bot.bat*' -or $_.CommandLine -like '*4b_jalankan_bot_minimize.bat*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo [OK] Bot dimatikan dan tidak akan menyala sendiri.
echo Untuk menyalakan lagi: buka 4_jalankan_bot.bat
pause
