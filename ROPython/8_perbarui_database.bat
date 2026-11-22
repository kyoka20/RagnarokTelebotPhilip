@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Perbarui database equip / kartu / skill
if not exist ".venv\Scripts\python.exe" (
  echo Belum di-install. Jalankan 1_install.bat dulu.
  pause
  exit /b 1
)
echo Sumber: roworlddb.com (database komunitas server SEA)
".venv\Scripts\python.exe" datagame.py %*
echo.
pause
