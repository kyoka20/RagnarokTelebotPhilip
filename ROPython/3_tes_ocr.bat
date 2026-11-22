@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Tes OCR
if not exist ".venv\Scripts\python.exe" (
  echo Belum di-install. Jalankan 1_install.bat dulu.
  pause
  exit /b 1
)
echo ==============================================
echo   MODE TES - cek apakah angka terbaca benar
echo ==============================================
echo Pastikan layar hasil "Damage Challenge" sedang tampil di game.
echo (Bisa juga: seret file gambar ke atas file .bat ini untuk mengetes gambar itu.)
echo.
".venv\Scripts\python.exe" tes_ocr.py %*
echo.
pause
