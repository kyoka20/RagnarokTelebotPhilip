"""Alat bantu: cari tahu chat_id Telegram kamu.

1. Isi token dulu di config.json
2. Jalankan script ini (5_cek_chat_id.bat)
3. Buka bot kamu di Telegram, kirim pesan apa saja (mis. "halo")
4. chat_id muncul di jendela ini. Salin ke config.json bagian "chat_id_diizinkan".
"""
from __future__ import annotations

import sys
import time

import umum
from telegram_api import Telegram, TelegramError, TelegramSementara


def main() -> int:
    umum.siapkan_konsol()
    try:
        cfg = umum.muat_config()
    except umum.ConfigError as e:
        print("MASALAH CONFIG:", e)
        return 2
    token = str(cfg["telegram"].get("token", "")).strip()
    if not token or token == umum.TOKEN_KOSONG:
        print("Token belum diisi. Buka config.json dan isi \"token\" dulu.")
        return 2
    tg = Telegram(token)
    try:
        info = tg.info_bot()
    except TelegramError as e:
        print(f"Token ditolak Telegram ({e}). Cek lagi tokennya.")
        return 2
    except TelegramSementara as e:
        print(f"Tidak bisa terhubung ke Telegram ({e}). Cek internet.")
        return 1
    print(f"Terhubung ke bot @{info.get('username')}.")
    print("Sekarang buka bot itu di Telegram dan kirim pesan apa saja.")
    print("Menunggu... (tutup jendela ini / Ctrl+C kalau sudah)\n")
    offset = None
    try:
        while True:
            try:
                for u in tg.ambil_update(offset, tunggu=20):
                    offset = u["update_id"] + 1
                    chat = (u.get("message") or {}).get("chat") or {}
                    if chat.get("id") is not None:
                        nama = chat.get("first_name") or chat.get("title") or ""
                        print(f"  chat_id = {chat['id']}    (dari: {nama})")
            except TelegramSementara:
                time.sleep(3)
            except TelegramError as e:
                print("Telegram menolak:", e, "(kalau bot utama sedang jalan, tutup dulu)")
                time.sleep(10)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
