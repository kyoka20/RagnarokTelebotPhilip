# Update jarak jauh (developer)

## Cara utama sejak 2026-11-24: auto-update dari GitHub
- Alur: dev edit di PC ini → commit + push ke `main` repo `kyoka20/RagnarokTelebotPhilip` → thread `loop_auto_update` (`bot.py`) di laptop Philip cek tiap 2 menit → ada commit baru → unduh zipball, ambil isi `ROPython/` yang berubah saja → pipeline aman yang sama dengan `/update` (`_terapkan_berkas_update`: cadangan, uji `import bot`, rollback kalau gagal, restart).
- Ringan: cek pakai ETag → tidak ada commit baru = GitHub balas 304 (0 byte, tak makan kuota). SHA terakhir di `log/auto_update_sha.txt`.
- Tidak pernah ikut terpasang: `DILARANG_UPDATE` (config.json, data, log, .venv, dll.) + `DILARANG_EKSTRA` (bat/ps1/vbs penjaga). Hanya `.py .json .txt .md`, maks 5 MB/file, sintaks dicek dulu.
- Perintah dev: `/auto_update` (status), `/auto_update owner/repo [branch]`, `/auto_update token ...`, `/auto_update cek` atau `/tarik_update` (tarik sekarang), `on/off`. Config: `auto_update` di `config.json` (repo, branch, token, interval_menit, aktif).
- Push = langsung sampai ke bot Philip. Jangan push kode yang belum dicek (`python -c "import bot"` di PC ini dulu).
- `/sync_log`: tiap 5 menit kirim ekor `bot.log` (≤200 KB) + ringkasan profil ke repo PRIVATE `kyoka20/ro-bot-logs` branch `logs` (`telemetry/`). Token disensor otomatis; menolak repo publik & branch main/master. Tidak berubah = 0 request. Baca log Philip dari sana (tak perlu minta `/log`).
- Perbaikan 24/11: `database/` & `database_ikon/` tidak ikut auto-update (`FOLDER_DIURUS_LAPTOP`; laptop unduh sendiri dari roworlddb, versi GitHub bisa lebih tua). Gagal karena internet → `lupakan_etag()` supaya dicoba lagi 2 menit kemudian (dulu terlewat sampai ada commit baru). Kode rusak (ValueError) / uji `import bot` gagal → kabar ke dev sekali. Saat Philip sedang `/input` (<30 menit) auto-update ditunda (tidak restart di tengah isian). `/sync_log` dulu tidak bisa dipanggil (tidak ada di daftar perintah dev) → sudah.
- Hemat CPU: `cek_nama_karakter` (OCR tengah layar tiap 6 dtk) dilewati saat AFK.
- Kode: `ROPython/autoupdate.py` (cek commit, unduh, sync log) + `bot.py` (`p_auto_update`, `_cek_auto_update`, `loop_auto_update`, `p_sync_log`, `loop_sync_log`).

## /update manual (cadangan, dibuat 2026-11-22)

Dibuat 2026-11-22. Semua kode di `ROPython/bot.py`, bagian `# developer (/update dari jauh)`.

- Developer = `DEV_DEFAULT` (konstanta atas `bot.py`) atau `telegram.chat_id_developer` di config.
- Perintah dev dicegat di `Bot.tangani` sebelum tabel perintah biasa: `/update`, `/update batal`, `/dev_mode`, `/log`, `/restart`, `/dev`.
- Laporan otomatis dikirim ke `Bot.penerima` (Philip + dev bila `dev_ikut_laporan` true di config, default true).
- `/update`: file dari caption/reply → `_baca_berkas_update` (cek sintaks .py, JSON, buang folder induk zip, lewati `DILARANG_UPDATE`) → cadangan `ROPython/cadangan_update/<waktu>/` + `_info_update.json` → tulis file → uji `python -c "import bot"` → gagal = `_pulihkan` → sukses = `_restart`.
- `_restart`: tulis `log/update_selesai.json`, `os._exit(3)`; `4_jalankan_bot.bat` menyalakan lagi (kode selain 0/2). Saat menyala, `_lapor_setelah_restart` memberi kabar.
- Jangan pernah update `4_jalankan_bot.bat` lewat /update saat bot jalan (bat yang sedang berjalan diedit = kacau).

- Setelah restart dari dev: Philip hanya dapat 1 baris ("🔧 Bot diperbarui, sudah aktif lagi."), pesan "Bot aktif" panjang dilewati; dev dapat daftar file.
- Philip minta (2026-11-22) tidak ada pesan spam/penjelasan panjang: kabar stat (`simpan_status`) & "Dipelajari otomatis" (`cek_enchant`) default diam, flag `kabar_stat` / `kabar_belajar` di config.

- Ringkasan otomatis malam (`loop_harian` → `Bot.ringkasan_malam` + `harian.ringkas`): 1 pesan pendek; `/hari` & `/tagihan` tetap versi lengkap (`_kelompok_tagihan` dipakai bersama).

- `karakter_terlihat`: ID sama + nick mirip (≥0.8) = salah baca OCR, diam & nick tidak ditimpa (dulu spam "Nick terbaca" 18x/hari).
- `/lihat24` = `/lihat 24` (angka nempel), `/list` = `/daftar`.
- Perintah paling sering dipakai Philip (log 10–22/11): /job, /lihat, /help, /daftar, /pindah, /input → jangan diubah perilakunya.
- Simulasi semua perintah: `scratchpad/skrip/simulasi.py <folder salinan>` (fake Telegram, jalankan di salinan, bukan folder asli).

- Pesan > 3900 huruf dipecah per baris (`telegram_api.potong_pesan`, dipakai `kirim_teks`, `Bot.balas`, `Bot.siarkan_teks`). Dulu dipotong `[:4000]` di tengah tag HTML → Telegram menolak → /daftar (37+ karakter) tidak membalas sama sekali (22/11). Jangan pakai `[:4000]` lagi.

- Banyak file sekaligus: file dari dev disimpan di `Bot.dok_tunggu` (10 menit). Album (`media_group_id`) → tunggu 4 dtk di thread lalu `_pasang_update` sekali; atau kirim file dulu lalu ketik `/update`. Satu update sekaligus (`kunci_update`).

- Data latih otomatis (22/11): tiap layar Enchant/Gem/Replace Enchant Stone BERUBAH (`Bot.cek_enchant`, pakai sidik `belajar.Pengamat`) → `latih.simpan_otomatis` simpan jpg + `catatan.jsonl` (teks OCR, bacaan) di `data/_latih/otomatis/<YYYYMMDD>/`. Diam, tanpa /record_train. Maks 300/hari, total 1,5 GB (hari tertua dihapus). Matikan: `"kumpul_data_latih": false`. Ambil: dev `/data_latih` (daftar) / `/data_latih YYYYMMDD` (zip ≤20 MB).

- Matikan sengaja (22/11): `/matikan ya` (`Bot.p_matikan`, semua pengguna) atau `9_matikan_bot.bat` → tulis `ROPython/BOT_DIMATIKAN.txt` (`FILE_DIMATIKAN`) → `jaga_bot.ps1` langsung `exit` kalau file ada; bot keluar kode 0 (bat tidak mengulang). `Bot.jalankan` menghapus file itu saat bot menyala lagi. Laptop restart/login ulang: `jaga_bot.ps1` hapus tanda kalau lebih tua dari jam mulai explorer.exe (cadangan: jam boot; explorer dipakai karena Fast Startup tidak mengubah jam boot) → bot autostart lagi. Dulu: ditutup → penjaga menyalakan lagi ≤5 menit.

- `/pemakaian [hari]` (dev, 22/11): `pemakaian.laporan` baca `log/bot.log(.1-.3)` → test DPS, perintah Philip (log `Perintah:` berakhiran ` [dev]` = dari dev, tidak dihitung), perintah `UTAMA` yang belum pernah dipakai, kirim otomatis, kesehatan (restart, 409 dobel, internet putus), 💡 saran. Log rotasi 4×1 MB ≈ 1–2 minggu.

- Perkiraan puncak (22/11, info saja, target tetap): `Bot.hasil_baru` → kalau `riwayat` karakter kosong (test pertama) tambah `perkiraan.teks`. Pola = puncak/pertama dari karakter lain dengan ≥5 test, 2 kelompok (awal < / ≥ 2,5jt), kuantil 20–80%, buang naik >3x; contoh <4 → `BAWAAN`. Uji mundur 19 karakter: meleset median 13%. User memilih ini (bukan target otomatis) karena 3jt = janji ke pembeli; semua profil masih target bawaan 3jt.

Kalau mau ubah:
- batas kelompok / pola bawaan / kalimat perkiraan → `perkiraan.py`
- daftar perintah yang dicek "belum dipakai" / aturan 💡 → `pemakaian.py` (`UTAMA`, bagian `saran`)
- batas data latih otomatis → `MAKS_OTOMATIS_HARI`, `MAKS_OTOMATIS_MB` di `latih.py`
- daftar file terlarang → `DILARANG_UPDATE`
- teks bantuan dev → `BANTUAN_DEV`
- siapa developer → `DEV_DEFAULT`

## /cek_laptop (28-11-2026)
- `/cek_laptop` atau `/cek_lemot` (siapa saja boleh): cari pelaku laptop lemot TANPA modul tambahan (PowerShell bawaan). Isinya: CPU, RAM, disk sibuk, CPU diperlambat (panas/baterai), main pakai baterai, mode hemat daya, bot RO dobel, Defender/Windows Update/Search sedang jalan, belum restart ≥7 hari, top 7 CPU & RAM, program autostart.
- Kode: `ROPython/cek_laptop.py` (`diagnosa`) + `bot.py` (`p_cek_laptop`, jalan di thread). Tes lokal: `PYTHONIOENCODING=utf-8 python cek_laptop.py`.
