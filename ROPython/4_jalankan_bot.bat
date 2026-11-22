@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Bot Pemantau DPS (boleh di-minimize, JANGAN ditutup)
if not exist ".venv\Scripts\python.exe" (
  echo Belum di-install. Jalankan 1_install.bat dulu.
  pause
  exit /b 1
)

:ulang
".venv\Scripts\python.exe" bot.py
if %errorlevel%==0 goto selesai
if %errorlevel%==2 goto selesai
echo.
echo Bot berhenti tidak wajar. Menyala lagi dalam 10 detik... (tutup jendela untuk batal)
timeout /t 10 /nobreak >nul
goto ulang

:selesai
echo.
pause
