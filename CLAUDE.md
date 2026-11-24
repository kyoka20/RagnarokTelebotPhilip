# Bot Telegram pemantau DPS (Philip)

Kode ada di `ROPython/`. Bot JALAN di laptop Philip (OCR layar game Ragnarok), BUKAN di PC ini.
PC ini = tempat saudaranya (developer, Telegram ID 1453123709) mengedit kode.

## Aturan wajib
- Jangan menjalankan `bot.py` di PC ini dengan token Philip (bentrok 409 dengan bot di laptop Philip). Untuk tes, buat bot tes sendiri di @BotFather.
- Jangan tampilkan / kirim isi token di `ROPython/config.json`.
- Kirim perubahan ke laptop Philip = **commit + push ke `main`** (github kyoka20/RagnarokTelebotPhilip); bot di laptop Philip menariknya sendiri ≤2 menit (auto-update). `/update` manual di Telegram masih bisa sebagai cadangan. Lihat peta.
- `ROPython.zip` (~400 MB) & `.venv/`, `python/`: jangan dibaca.
- `.venv` menunjuk ke path Philip; untuk cek kode di sini pakai `ROPython/python/cpython-3.12.15-windows-x86_64-none/python.exe` + `PYTHONPATH=ROPython/.venv/Lib/site-packages`.

## Peta
| Catatan | Baca saat tugas soal ... |
|---|---|
| [dokumen/peta/update-jarak-jauh.md](dokumen/peta/update-jarak-jauh.md) | auto-update GitHub, /sync_log, /update, /dev_mode, /log, restart, kirim perubahan ke laptop Philip |
| [dokumen/peta/rumus-damage.md](dokumen/peta/rumus-damage.md) | rumus damage, saran racikan, panel Statistics, stat per test |
| [dokumen/peta/file-game.md](dokumen/peta/file-game.md) | isi file game RO New World, datamining, rumus damage |
| `ROPython/README.md` | cara pakai bot, daftar perintah, config |
