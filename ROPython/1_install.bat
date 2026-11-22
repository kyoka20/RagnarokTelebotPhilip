@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Install Bot Pemantau DPS
echo ==============================================
echo   INSTALL BOT PEMANTAU DPS (cukup sekali)
echo ==============================================
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  if defined PY (
    echo Membuat lingkungan Python...
    %PY% -m venv .venv
  ) else (
    rem Tidak ada Python biasa: pakai uv, dan simpan Python-nya DI DALAM folder ini
    rem supaya tidak bergantung pada lokasi lain di komputer.
    set "UV_PYTHON_INSTALL_DIR=%~dp0python"
    where uv >nul 2>nul && uv python install 3.12 && uv venv --python 3.12 --managed-python .venv
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo [X] Python belum terpasang.
  echo     Install dulu dari https://www.python.org/downloads/  ^(versi 3.12^)
  echo     dan CENTANG "Add python.exe to PATH" saat install.
  echo     Setelah itu jalankan file ini lagi.
  echo.
  pause
  exit /b 1
)

echo Memasang paket yang dibutuhkan (butuh internet)...
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if errorlevel 1 (
  uv pip install --python ".venv\Scripts\python.exe" -r requirements.txt
) else (
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
)
if errorlevel 1 (
  echo.
  echo [X] Gagal memasang paket. Cek koneksi internet lalu coba lagi.
  pause
  exit /b 1
)

if not exist "config.json" (
  copy /y "config.example.json" "config.json" >nul
  echo File config.json dibuat dari contoh.
)

echo.
echo [OK] Install selesai.
echo Langkah berikutnya:
echo   1. Buka config.json pakai Notepad, isi token bot.
echo   2. Jalankan 5_cek_chat_id.bat untuk tahu chat_id, isi ke config.json.
echo   3. Jalankan 3_tes_ocr.bat untuk tes, lalu 4_jalankan_bot.bat.
echo      (2_setup_area.bat tidak wajib, bot mencari angka DPS sendiri di layar.)
echo.
pause
