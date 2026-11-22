# Rumus damage & data untuk saran racikan

Dibuat 2026-11-22. Tujuan: bot bisa menyarankan batu/kartu/equip/skill dengan hitungan "%DPS naik per biaya".

## Fakta yang sudah diketahui
- Tidak ada rumus damage publik (dicek: roworlddb, rtnw.online, forum/reddit). Hitungan akhir damage di server.
- Studi Sniper (PDF dari user, "Ragnarok_Sniper_Study.pdf", Agt 2026; salinan teks tidak disimpan):
  - Angka skill & stat ada di config client: `SkillConfigTable`, `BuffConfigTable`, `StuntAttributeLibraryConfig` (Special Skill senjata, efeknya lewat Buff, TIDAK ada di data skill), `AttributePointNeedConfigTable`. Sel kosong = nilai default (`fieldIndexToDefaultValue`).
  - Ranged: P.ATK = rasio_senjata × (ATK senjata + DEX + 0,2·LUK). Kecepatan serang = min((300+4·AGI+DEX)/190,62; 7).
  - Panel **Statistics** pasca-tempur = damage per skill + persen. Rasio 2 sumber dalam 1 test membuat DEF/crit/bonus global saling coret.
  - Noise 1 test ±5–9% (kontrol manual) → beda <5% harus diulang beberapa test.
  - Bobot PDMG%/Final DMG/ras/ukuran/elemen/CRIT DMG digabung bagaimana: BELUM diketahui → perlu eksperimen ubah-satu-hal.
- Deskripsi stat di `database/equipment.json` (attr): ATK% hanya untuk ATK dari gear; STR = ATK melee +1, DEX = ATK ranged +1, LUK = CRIT +0,3 & ATK +0,2.
- Data skill roworlddb (`database/skill/<job>.json`): pve_percent, pve_flat, cooldown, gcd, cast, elemen per level.
- Data monster (2.888, rtnw.online = ekspor client SEA): `ROPython/monster.py` -> `ROPython/database_tetap/monster.json` (ras, ukuran, elemen, HP, DEF, M.DEF). Folder `database_tetap` tidak ikut diganti saat database roworlddb diperbarui & boleh lewat /update. Perbarui: `python monster.py` (di PC ini SSL `requests` gagal; unduh pakai curl lalu `monster._ringkas`).
  - Sasaran test 'Damage Test Dummy (Humanoid, Medium)' tidak punya angka stat di data → dipakai 'DMG Test Dummy' (Lv5, Mech/Small): DEF 100, M.DEF 50 = PERKIRAAN. Tampil di `/sasaran`.
- Data bahan meramu (rtnw.online, belum ada di roworlddb): `ROPython/datartnw.py` -> `database_tetap/` `refine.json` (stat per +1 refine, 2.616 equip; `teks_refine(id, N)`), `rune.json` (33 efek rune per level + resonansi), `pet.json` (31 pet, efek per bond), `apocalypse.json` (999 trait). Perbarui: `python datartnw.py`. Id stat refine 29/32/35/38/310/312/314 tidak ada di atribut roworlddb; artinya (ATK refine, P.DMG tetap, dll.) = tafsiran ro-sim, belum pasti (`ATTR_REFINE`).
- Sengaja TIDAK diambil: biaya refine, harga shop, peluang fusion kartu (bukan bahan hitung damage).
- Kalkulator komunitas: ro-sim.vercel.app (github MuhammadLuqman-99/ro-sim, tanpa lisensi → kode jangan disalin). Rumusnya ASUMSI (semua bonus dikali, DEF diabaikan, STR/DEX tidak jadi ATK). Datanya dari rtnw.online. Belum ada rumus RTNW yang terbukti di internet (dicek 22/11/2026, termasuk forum CN/TW).

## Hasil bongkar statis file game (REA, 22/11/2026, game ditutup)
Detail bukti teknis: [[file-game]]. Kesimpulan: **tidak ada rumus yang bisa dibaca dari file game** tanpa membongkar enkripsi (tidak dilakukan).
- [KODE GAME] Nama yang terbaca polos soal damage di client semuanya **tampilan**: `SGEngine.UI.DamageFloaterQueue/DamageFloaterStruct`, `DamageTextAnimation*`, `DamageTextManager`, `HurtHighlightConfig`, `SkillHurtScopeEffect`. Tidak ada kelas Battle/Formula/Calc yang terbaca.
- [KODE GAME, nama setengah terbaca] Field config monster di metadata: `PhyAtkWeapon`, `MagicAtkWeapon`, `CritDef`, `CritDamRatio`, satu lagi `CritDm?Ratio` (huruf tengah rusak), `Aspd`, `SpecialAttributes`. Artinya:
  - ATK monster dipisah "ATK dari senjata" (fisik & magic) → mirip pemain (ATK senjata dikali rasio, cocok dgn studi Sniper).
  - **CritDef** = tahanan crit milik sasaran (mengurangi peluang/damage crit). **CritDamRatio** = pengali damage crit. Ada 2 faktor crit → crit dihitung lewat 2 pengali (DUGAAN: CRIT DMG% penyerang dikurangi tahanan sasaran).
- [KODE GAME, setengah terbaca] Enum gaya angka: `Element_Plus_Attack`, `Element_Minus_Attack`, `..._Crit`, `..._Knock` → angka damage diberi warna beda saat elemen menguntungkan/merugikan (DUGAAN: hanya gaya tampilan).
- [DUGAAN kuat] Hitungan damage di **server**: logika game (`Assembly-CSharp`) dikirim sebagai DLL hot-update terenkripsi, tabel config pakai **Luban** di bundle terenkripsi, client hanya punya antrean angka untuk ditampilkan.
- Tidak bisa diketahui: urutan penjumlahan/perkalian bonus (P.DMG%, Final DMG, ras, ukuran, elemen), rumus DEF, nilai tabel elemen.

## Rencana uji pakai bot (memastikan rumus)
Prinsip: ubah SATU hal, uji ≥3 kali per kondisi (noise ±5–9%), sasaran & rotasi sama.
1. **Dijumlah atau dikali?** Uji A: +X% P.DMG. Uji B: +Y% bonus ras. Uji C: keduanya. Kalau C ≈ A+B → dijumlah; kalau C ≈ A×B → dikali. Ulangi untuk ukuran/elemen/Final DMG.
2. **Crit:** bandingkan DPS dengan CRIT DMG% berbeda (CRIT rate sama). Hasil dibagi peluang crit → pengali crit. Uji di sasaran lain untuk melihat efek `CritDef`.
3. **DEF:** sasaran sama, tambah "ignore DEF"/penetrasi → besar kenaikan menunjukkan bentuk rumus DEF (kurang tetap vs persen).
4. **Elemen:** skill elemen ke monster elemen berbeda (`monster.json`) → tabel pengali elemen.
5. Pakai panel **Statistics** (rasio antar-skill dalam 1 test) supaya bonus global saling coret; `test_stat.jsonl` mencatat stat tiap test sebagai bahan regresi.

## Pengumpulan data (sudah jalan)
- `ROPython/statistik.py` + `Bot.cek_statistik/simpan_statistik` di `bot.py`: baca panel Statistics → `data/<pid>/statistik.jsonl` + gambar `data/<pid>/statistik/`. Deteksi: kata "Statistic" + ≥2 persen. Tata letak panel asli BELUM pernah dilihat developer → cek gambar tersimpan lalu rapikan `statistik.baca`. Config `kabar_statistik`.
- `Bot.catat_stat_test`: stat berlaku saat tiap test → `data/<pid>/test_stat.jsonl`; pengingat bila DPS berubah ≥3% tapi Detailed Stats belum dibuka sejak test lalu. Config `ingatkan_stat`.

## Langkah berikutnya
1. Lihat gambar panel Statistics asli, rapikan parser.
2. Daftar eksperimen ubah-satu-hal untuk Philip; modul pengurai (dikali vs dijumlah, bobot).
3. Baca halaman Equipment/kartu; lalu perintah `/racik`.
