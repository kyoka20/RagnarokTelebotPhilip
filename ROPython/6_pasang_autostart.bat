@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Memasang autostart bot (jalan saat login + dicek tiap 5 menit)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"' + '%~dp0jaga_bot.ps1' + '\"') -WorkingDirectory '%~dp0';" ^
  "$t1 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME;" ^
  "$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5);" ^
  "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2);" ^
  "Register-ScheduledTask -TaskName 'Bot Pemantau DPS' -Action $a -Trigger $t1,$t2 -Settings $s -Description 'Menjaga bot pemantau DPS tetap jalan' -Force | Out-Null"
if errorlevel 1 (
  echo [X] Gagal memasang autostart.
) else (
  echo [OK] Autostart terpasang. Untuk melepas: klik dua kali 7_hapus_autostart.bat
)
pause
