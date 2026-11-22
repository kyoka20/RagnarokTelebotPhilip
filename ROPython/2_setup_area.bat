@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Setup Area DPS
if not exist ".venv\Scripts\python.exe" (
  echo Belum di-install. Jalankan 1_install.bat dulu.
  pause
  exit /b 1
)
echo ==============================================
echo   SETUP AREA
echo ==============================================
echo 1. Pastikan layar hasil "Damage Challenge" sedang tampil di game.
echo 2. Setelah tekan tombol, layar akan jadi agak gelap (itu foto layar, bukan game).
echo 3. DRAG mouse mengotaki bagian hasil: dari baris "Total DMG"
echo    sampai baris "Highest Solo DMG Record", tulisan dan angkanya ikut masuk.
echo 4. Tekan ENTER untuk simpan, ESC untuk batal.
echo.
echo Profil yang diatur = profil aktif di config.json.
echo.
pause
".venv\Scripts\python.exe" setup_area.py %*
echo.
pause
