# Bot Pemantau DPS Ragnarok → Telegram

Bot ini **melihat layar** (screenshot), **membaca angka** "DMG Per Second" di layar hasil
Damage Challenge, lalu **mengirim notifikasi ke Telegram**.

> **Aman untuk akun:** script hanya mengambil screenshot, sama seperti aplikasi perekam layar.
> Tidak ada klik, tekan tombol, macro, baca memory, atau injeksi ke game.

---

## Cara kerja singkat

1. Kamu main seperti biasa: ganti equipment/card → jalankan Damage Challenge.
2. Saat layar hasil (VICTORY) muncul, bot membaca angkanya dalam beberapa detik.
3. **Setiap** hasil langsung disimpan. Report teks dikirim duluan (sampai dalam hitungan detik),
   lalu foto jendela game (gambar karakter + angka) menyusul. Report menyebut naik / turun / sama
   dibanding DPS terbaik di sesi ini.
   Saat kamu belum mulai test (tidak ada layar hasil), bot diam dan tidak mengirim peringatan apa pun.
4. Kapan saja dari HP: `/status`, `/daftar`, `/rapor`, dan lain-lain.

Bot mengecek layar tiap **2 detik** (bisa diubah). Kalau layar hasil sedang tidak tampil,
itu dianggap normal, bukan error.

---

## Langkah 1 — Install Python

1. Buka <https://www.python.org/downloads/> dan unduh **Python 3.12** (atau 3.11 / 3.13).
2. Jalankan installer. **CENTANG "Add python.exe to PATH"** di layar pertama, baru klik *Install Now*.
3. Klik dua kali **`1_install.bat`**. Tunggu sampai muncul `[OK] Install selesai`.

## Langkah 2 — Buat bot Telegram

1. Di Telegram, cari **@BotFather** (yang ada centang biru).
2. Kirim `/newbot`.
3. Isi nama bot (bebas), lalu username bot (harus diakhiri `bot`, misalnya `dps_saya_bot`).
4. BotFather memberi **token**, bentuknya seperti `1234567890:AAH...`. Salin.
5. Buka **`config.json`** dengan Notepad. Ganti `ISI_TOKEN_DARI_BOTFATHER` dengan token itu
   (tanda kutipnya jangan dihapus).

> Token itu seperti password. Jangan dibagikan dan jangan kirim `config.json` ke orang lain.

## Langkah 3 — Dapatkan chat_id

1. Klik dua kali **`5_cek_chat_id.bat`**.
2. Buka bot kamu di Telegram, tekan **Start**, kirim pesan apa saja (misalnya `halo`).
3. Di jendela hitam muncul `chat_id = 987654321`. Salin angkanya.
4. Di `config.json`, ganti `123456789` dengan angka itu:
   ```json
   "chat_id_diizinkan": [987654321]
   ```
   Mau 2 orang yang boleh pakai? Tulis `[987654321, 111222333]`.
5. Tutup jendela hitam itu.

Bot **hanya** menjawab chat_id yang ada di daftar ini. Orang lain diabaikan.

## Langkah 4 — Isi config, setup area, tes, jalankan

**a. Config** (`config.json`) — yang perlu diisi cuma token dan chat_id. Sisanya boleh nanti:

| Pengaturan | Arti |
|---|---|
| `mode` | `"perubahan"` = notif tiap ada hasil DPS baru. `"target"` = notif sekali saat tembus target |
| `interval_detik` | Jarak antar cek layar (detik). Default 1, jadi hasil terdeteksi sekitar 1–2 detik setelah layar VICTORY muncul. Bot hanya membaca tulisan kalau layar berubah, jadi ringan. Kalau PC terasa berat, naikkan ke 3 |
| `judul_jendela_game` | Judul jendela game. Bot **hanya** membaca jendela ini, jadi gambar hasil DPS di WhatsApp/Telegram/browser tidak ikut terbaca. Default `"Ragnarok: The New World"`. Kosongkan (`""`) untuk membaca seluruh layar |
| `kirim_layar_penuh` | `true` = notif juga menyertakan foto satu layar penuh |
| `peringatan_gagal_berturut` | Kirim peringatan setelah sekian kali gagal baca berturut-turut. Default `0` = mati |
| `peringatan_tanpa_hasil_menit` | Kirim peringatan kalau sekian menit tidak ada hasil baru. Default `0` = mati |
| `profil` → `nama`, `target`, `nick`, `job` | Nama akun pelanggan, target DPS, nick dan job karakternya (isi lewat `/input` atau `/job`; nick juga terbaca otomatis dari halaman info karakter) |

**b. Setup area — TIDAK WAJIB.** Secara bawaan bot memakai **mode otomatis**: bot mencari sendiri
tulisan `DMG Per Second` di seluruh layar, jadi tidak ada yang perlu ditandai. Langsung ke langkah c.

Setup area hanya perlu kalau mode otomatis salah tangkap (misalnya ada jendela lain yang juga
menampilkan tulisan `DMG Per Second`). Caranya: tampilkan layar hasil di game, klik dua kali
`2_setup_area.bat`, **drag** mengotaki dari baris `Total DMG` sampai `Highest Solo DMG Record`,
tekan **Enter**. Untuk kembali ke mode otomatis, ubah `"area"` di `config.json` jadi `null`.

**c. Tes** — tampilkan layar hasil di game, klik dua kali **`3_tes_ocr.bat`**, lalu dalam 5 detik
pindah ke jendela game. Cocokkan angka yang tampil dengan yang ada di game.
Mau tes tanpa game? Seret salah satu gambar di folder `contoh` ke atas `3_tes_ocr.bat`.

Folder `contoh/screenshot` berisi 287 screenshot asli Damage Challenge + `kunci_jawaban.json`.
Untuk menguji bot ke semuanya sekaligus (misalnya setelah kode diubah):
`.venv\Scripts\python.exe tes_ocr.py --regresi`

**d. Jalankan** — klik dua kali **`4_jalankan_bot.bat`**. HP akan menerima pesan "Bot pemantau DPS aktif".
Jendela hitamnya boleh di-minimize, **jangan ditutup**. Mau langsung minimize? Pakai
`4b_jalankan_bot_minimize.bat`.

**Mematikan bot (sengaja):** ketik `/matikan ya` di Telegram, atau klik dua kali `9_matikan_bot.bat`.
Bot mati dan penjaga autostart TIDAK menyalakannya lagi (ada file `BOT_DIMATIKAN.txt`), sampai laptop
di-restart / login ulang (lalu otomatis menyala), atau Anda buka `4_jalankan_bot.bat` (file tanda terhapus sendiri). Cuma jeda sebentar: `/stop` lalu `/start`.
Menutup jendela hitam saja TIDAK cukup kalau autostart terpasang: paling lambat 5 menit bot menyala lagi.

**Autostart (disarankan):** klik dua kali `6_pasang_autostart.bat` sekali saja. Setelah itu bot otomatis
jalan saat login Windows, dan dicek tiap 5 menit. Kalau mati, bot dinyalakan lagi sendiri (catatan di
`log/penjaga.log`). Untuk melepas: `7_hapus_autostart.bat`.

> **Penting:** game harus tetap **terlihat di layar**. Jangan di-minimize dan jangan tertutup
> jendela lain di bagian area hasil, karena bot membaca apa yang tampil di layar.

---

## Perintah di Telegram

| Perintah | Fungsi |
|---|---|
| `/input` | Isi / ubah data pembeli langkah demi langkah dengan tombol: ID, nick, job, kontak, paket, target, status bayar, catatan. ID yang sudah ada = data diperbarui. `/batal` untuk berhenti |
| `/daftar` | Semua karakter yang pernah dikerjakan: nick, job, DPS terakhir. ▶️ = yang aktif sekarang |
| `/lihat 2` | Foto + detail hasil terakhir karakter nomor 2 (boleh juga nick atau ID) |
| `/pilih 2` | Jadikan karakter nomor 2 yang aktif dites (kalau tidak sempat membuka halaman info karakter) |
| `/rapor` | **Gambar rapor** untuk pembeli: DPS awal vs DPS terbaik, kenaikan %, target, foto sebelum & sesudah. `/rapor 2` = karakter nomor 2. Tinggal teruskan gambarnya |
| `/arsip` | File Excel (.xlsx) rapi: sheet **Ringkasan** (semua pembeli, DPS awal/terbaik/terakhir, kenaikan, progres target, status bayar berwarna) dan sheet **Riwayat Test** (semua test). Salinannya juga di `data/arsip_pemain.xlsx` |
| `/target 5jt` | Ganti target karakter aktif. Boleh `3jt`, `3.5M`, `750k` |
| `/job Knight` | Isi / koreksi job karakter aktif. `/job` saja = lihat job sekarang |
| `/hari` | **Ringkasan hari ini**: total waktu kerja, jam mulai-selesai, istirahat, waktu & kenaikan DPS per karakter. `/hari kemarin` atau `/hari 20/11` = hari lain. Waktu dihitung dari mulai test pertama (jam hasil − lama test) sampai hasil test terakhir; jeda lebih dari `jeda_istirahat_menit` (default 30) di `config.json` dianggap istirahat. Lebih dari `afk_menit` (default 5) tidak memakai mouse/keyboard di jendela game (diam, atau sedang browsing/YouTube/chat) = AFK, dipotong dari waktu kerja (dicatat di `data/afk.csv`; hanya membaca jam idle & judul jendela aktif dari Windows, tidak menyentuh game) |
| `/tagihan` | Pembeli yang **belum lunas**. Yang targetnya sudah tercapai ditaruh paling atas (siap ditagih). Karakter aktif yang data pembelinya belum diisi juga diingatkan |
| `/saran nama` | Saran build singkat 1 karakter (salah ketik / sebagian nama tidak apa-apa, kosong = karakter aktif): rekor vs target + tren, bonus stat yang **terbuang** di test + kartu pengganti, dan **urutan batu yang paling murah dinaikkan** (Weapon/Acc/Head/Back saja, HP/DEF disembunyikan). Data enchant per karakter terisi otomatis saat halaman Enchant karakter itu dibuka |
| `/batu` | Saran batu enchant (set) terbaik per slot untuk DPS: Weapon/Accessory = Swift Attack, Headwear/Backwear = Frenzy III; slot lain set bertahan (tidak menambah angka test). `/batu head` = satu slot saja |
| (otomatis) | **Belajar halaman Enchant sendiri**: setiap kali halaman Enchant terbuka (atau saat `/record_train`), bot membaca detail gem (tekan lama ikon gem) dan "Set Effect: ... Lv.N", menyimpannya di `database_lokal/enchant_belajar.json`, lalu mengabari di Telegram. Hasilnya langsung muncul di `/db` dan `/batu`. Tidak perlu Claude |
| `/sasaran` | Sasaran Damage Challenge (default: Damage Test Dummy Humanoid = Human/Demi-Human, Medium, Neutral; atur di `config.json` → `sasaran_test`), DEF & M.DEF sasaran (data monster `database_tetap/monster.json` dari rtnw.online; perbarui: `python monster.py`) + semua kartu yang menambah damage ke sasaran itu. `/stat` dan pesan "Stat tersimpan" juga menunjukkan bonus yang **terpakai** vs **terbuang** saat test |
| `/record_train` (atau `/rekam`) | **Mode train**: bot menyimpan gambar jendela game setiap kali layar berubah, selagi Anda membuka halaman Enchant (tekan lama tiap gem), Insert Card, Detailed Stats, Skills, dll. Ketik `/stop` untuk berhenti (pemantauan DPS tetap jalan). Setelah berhenti, gambar dibaca & dikelompokkan per halaman, ringkasan dikirim. Disimpan di `data/_latih/<waktu>/` (+ `rekaman.json` berisi teks tiap gambar) untuk dipelajari Claude. Otomatis berhenti setelah 60 menit / 1.500 gambar |
| (otomatis) | **📊 Damage per skill**: setelah test, tekan tombol **Statistics** (kanan bawah layar VICTORY). Bot membaca damage & persen tiap skill, menyimpannya di `data/<profil>/statistik.jsonl` (+ gambar panel di `data/<profil>/statistik/`), lalu mengirim ringkasan. Kalau jumlah persen bukan ±100%, scroll panelnya. Matikan kabar: `"kabar_statistik": false` |
| (otomatis) | **Stat per test**: tiap hasil test, stat terakhir dari Detailed Stats ikut dicatat di `data/<profil>/test_stat.jsonl` (bahan membongkar rumus damage). Kalau DPS berubah ≥3% padahal Detailed Stats belum dibuka sejak test lalu, laporan memberi pengingat. Matikan: `"ingatkan_stat": false` |
| `/stat` | Stat karakter aktif (ATK, ATK%, PDMG, CRIT, Ignore P.DEF, dll). `/stat 2` = karakter nomor 2 |
| (otomatis) | **📋 Baca halaman Status**: buka *Character Info > Detailed Stats* di game lalu scroll sampai bawah; bot menyimpan angkanya (data/&lt;profil&gt;/status_log.jsonl). Laporan DPS berikutnya menampilkan **🔧 stat yang berubah sejak test lalu** |
| (otomatis) | **🌙 Ringkasan harian** (1 pesan singkat: jam kerja, jumlah test, 3 DPS naik terbesar, tembus target, siap ditagih; detail lewat `/hari` & `/tagihan`) dikirim sendiri jam `ringkasan_harian_jam` (default 23:30), hanya kalau hari itu ada test. Matikan: isi `""` |
| (otomatis) | **📊 Rapor otomatis** saat target tembus: gambar rapor langsung dikirim, tinggal diteruskan ke pembeli. Matikan: `"rapor_otomatis_saat_target": false` |
| (otomatis) | **⚠️ Test terlewat**: kalau Rekor di layar naik tanpa ada test yang tercatat, laporan berikutnya memberi tahu (perkiraan DPS-nya juga) |
| (otomatis) | **💡 Saran** di bawah tiap laporan DPS, maksimal 2 baris: naik/turun *nyata* atau masih dalam batas acak karakter itu (diukur dari test-test sebelumnya), rekor lama jauh lebih tinggi, 1 jam tanpa kenaikan nyata, target tinggal sedikit. Hanya dari angka hasil test (belum dari isi equip). Matikan: `"saran_otomatis": false` di `config.json` |
| (otomatis) | **📈 Perkiraan puncak** di laporan test PERTAMA karakter baru: kira-kira DPS tertinggi yang bisa dicapai, dari pola karakter-karakter sebelumnya (yang awalnya lemah biasanya naik ±35–75%, yang sudah kuat ±5–17%). Kalau perkiraan di bawah target: ⚠️ target kemungkinan berat. Target TIDAK diubah. Matikan: `"perkiraan_puncak": false` |
| `/db` | **Database equip / kartu / skill / gem / set enchant** server SEA: `/db Dracula`, `/db skill Acid Terror`, `/db equip Hurricane Fury`, `/db frenzy 3`, `/db dom gem`. Salah ketik tidak apa-apa (kalau tidak persis, bot menulis "Mungkin maksud Anda"). Set enchant & angka gem per level dipelajari dari layar Enchant game, disimpan di `database_lokal/enchant.json` (boleh diedit). `/db update` = cek pembaruan. Sumber: [roworlddb.com](https://roworlddb.com/sea/) (database komunitas, bukan resmi). Disimpan di folder `database/`, dicek otomatis sekali sehari; manual: `8_perbarui_database.bat` |
| `/status` | Bot hidup? DPS terbaik, target, jam cek terakhir |
| `/ss` | Screenshot layar sekarang |
| `/stop` / `/start` | Jeda / lanjutkan pemantauan |
| `/help` | Daftar perintah |

Menu perintah ini juga muncul otomatis saat mengetik `/` di Telegram.

Perintah lama `/profil`, `/nick`, `/laporan`, `/riwayat`, `/sesibaru`, `/mode`, `/interval` sudah dihapus:
gantinya `/pilih`, `/input`, `/rapor`, dan `/lihat`. Mode notifikasi dan jarak cek masih bisa diubah di `config.json`.

### Alur kerja per pelanggan

1. `/input` → isi ID, nick, job, kontak, paket, target, status bayar pembeli.
2. Login ke karakter pembeli, buka halaman info karakter (yang ada tulisan `ID:...`) sekitar 3 detik.
   Bot mengenali karakter dari ID-nya dan langsung memakai data dari langkah 1. Kalau ID-nya belum
   pernah diinput, catatan baru dibuat dan bot mengingatkan untuk `/input`.
3. Jalankan Damage Challenge **sebelum** meracik → ini jadi "DPS awal" di rapor.
4. Racik, tes, racik, tes. Tiap hasil otomatis tercatat dan dilaporkan.
5. Selesai → `/rapor`, teruskan gambarnya ke pembeli.

**Job** diambil dari data yang Anda isi (`/input` atau `/job`), karena halaman info karakter di game
tidak menuliskan nama job. Tebakan dari ikon kecil di HUD hanya dipakai kalau job belum diisi, dan
tidak pernah menimpa data Anda.

**Teks di bawah rapor** diatur di `config.json` → `"rapor_catatan_kaki"` (misalnya akun TikTok Anda).

**Pesan otomatis yang dibuat diam** (tetap dicatat di belakang layar): stat karakter yang terbaca dari Detailed Stats
(lihat kapan saja lewat `/stat`, lengkap dengan saran kartu) dan "Dipelajari otomatis" dari layar Enchant (masuk `/db`).
Mau dikabari lagi: `"kabar_stat": true` / `"kabar_belajar": true` di `config.json`.

### Update dari jauh (developer)

Developer (ID Telegram di `DEV_DEFAULT` di `bot.py`, atau `"chat_id_developer": [...]` di bagian `telegram` config) bisa
memperbarui bot tanpa Anda copy file manual. Bot harus dijalankan lewat `4_jalankan_bot.bat` / autostart supaya bisa menyala sendiri lagi.

| Perintah | Fungsi |
|---|---|
| `/update` | Kirim file `.py` atau `.zip` (isi file yang diubah saja) dengan caption `/update`. Bot cek kode → simpan cadangan di `cadangan_update/` → ganti file → uji `import bot` (kalau error, file lama dikembalikan otomatis) → restart. `config.json`, `data/`, `log/`, `database_lokal/` tidak pernah ditimpa |
| `/update batal` | Kembalikan file dari update terakhir, lalu restart |
| `/dev_mode` | Developer ikut menerima laporan otomatis on/off (default on) |
| `/log` | 40 baris terakhir log bot (`/log 100`) |
| `/restart` | Restart bot |

---

## Di mana datanya?

| Lokasi | Isi |
|---|---|
| `data/<profil>/riwayat.csv` | Semua hasil test (waktu, DPS, Total DMG, rekor). Bisa dibuka di Excel |
| `data/<profil>/gambar/` | Foto jendela game tiap hasil yang disimpan (dipakai untuk `/lihat` dan `/rapor`) |
| `log/bot.log` | Catatan kejadian dan error |

---

## Troubleshooting

**Angka salah baca / tidak terbaca**
- Jalankan `3_tes_ocr.bat` dan lihat bagian "Semua tulisan yang terbaca".
- Mode otomatis: bot mengambil gambar langsung dari jendela game (seperti "Window Capture" di OBS),
  jadi tetap terbaca walau ketutup Telegram/Chrome/WA. Yang tidak boleh: game di-**minimize**.
  Kalau jendela game digeser, bot menemukannya lagi sendiri.
- Mode otomatis salah tangkap angka dari jendela lain (browser, chat, README ini)? Tutup jendela
  itu, atau pakai `2_setup_area.bat` supaya bot hanya melihat satu kotak.
- Kalau pakai setup area: tulisan `DMG Per Second:` harus ikut masuk kotak, dan setup harus
  diulang kalau jendela game digeser atau diubah ukurannya.
- Buka `data/tes_area.png` untuk melihat persis apa yang dibaca bot.
- Masih salah? Di `config.json` bagian `ocr`, coba `"perbesar": 3`.

**Screenshot hitam / peringatan "layar hitam"**
- Game sedang *fullscreen exclusive*. Ubah di pengaturan game ke **Borderless** atau **Windowed**.
- Layar monitor mati/sleep: matikan sleep di Settings Windows → System → Power.

**Notif tidak masuk**
- Sudah tekan **Start** di chat bot? Bot tidak bisa mengirim pesan duluan ke orang yang belum pernah chat.
- chat_id benar? Cek lagi dengan `5_cek_chat_id.bat` (tutup bot utama dulu).
- Di mode `target`, notif hanya muncul saat DPS **tembus** target. Ubah `"mode"` di `config.json` jadi `"perubahan"`.
- Lihat `log/bot.log`. Kalau internet putus, bot mencoba ulang sendiri sampai 30 menit.

**"Token ditolak Telegram"** — token salah ketik. Salin ulang dari @BotFather.

**"config.json rusak"** — biasanya kurang koma atau tanda kutip. Bandingkan dengan `config.example.json`.

**Log menulis "dijalankan di tempat lain juga (dobel)"** — bot terbuka 2 kali. Tutup salah satu.

**Mau ada peringatan kalau game crash / lama tidak ada hasil?** Isi `peringatan_tanpa_hasil_menit`
(misalnya `30`) dan/atau `peringatan_gagal_berturut` (misalnya `3`). Secara bawaan keduanya mati.

**Layar hasil di game beda bahasa / labelnya lain** — ubah `"label"` di profil sesuai tulisan di layar.

### Cadangan: Tesseract (hanya kalau OCR Windows tidak jalan)

Bot memakai OCR bawaan Windows dulu. Kalau itu gagal, bot otomatis memakai Tesseract **bila terpasang**:

1. Unduh installer dari <https://github.com/UB-Mannheim/tesseract/wiki> dan install di lokasi bawaan.
2. Selesai. Kalau dipasang di lokasi lain, isi `"tesseract_path"` di `config.json`.
3. Untuk memaksa pakai Tesseract: `"mesin": "tesseract"`.
