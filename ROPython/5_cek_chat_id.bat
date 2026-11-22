@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cek chat_id Telegram
if not exist ".venv\Scripts\python.exe" (
  echo Belum di-install. Jalankan 1_install.bat dulu.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" cek_chat_id.py
echo.
pause
