@echo off
chcp 65001 >nul
echo Melepas autostart bot...
powershell -NoProfile -Command "Unregister-ScheduledTask -TaskName 'Bot Pemantau DPS' -Confirm:$false" && echo [OK] Autostart dilepas. Bot yang sedang jalan tidak ikut ditutup.
pause
