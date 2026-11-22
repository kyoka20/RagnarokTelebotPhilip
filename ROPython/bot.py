"""BOT PEMANTAU DPS - loop pemantauan + perintah Telegram.

ATURAN: script ini HANYA mengambil screenshot dan membaca angkanya.
Tidak ada klik, tekan tombol, baca memory, atau injeksi ke game.

Jalankan lewat 4_jalankan_bot.bat (atau: python bot.py).
"""
from __future__ import annotations

import copy
import difflib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime, timedelta

import requests

import bacabuild
import belajar
import catatan
import datagame
import harian
import job
import latih
import pemakaian
import autoupdate
import perkiraan
import layar
import ocr
import rapor
import rumus
import saran
import saranbuild
import sasaran
import statistik
import umum
import visual
from telegram_api import Pengirim, Telegram, TelegramError, TelegramSementara, potong_pesan

BANTUAN = """<b>Daftar perintah</b>

<b>Pembeli jasa</b>
/input - isi / ubah data pembeli (ID, nick, job, kontak, paket, bayar)
/daftar - semua karakter + DPS terakhir
/lihat 2 - foto & detail karakter no. 2
/pilih 2 - jadikan karakter no. 2 yang aktif dites
/pindah - pindahkan hasil DPS terakhir ke karakter aktif (kalau salah masuk)
/rapor - gambar rapor premium (sebelum vs sesudah + grafik) untuk dikirim ke pembeli
/rapor 2 - rapor karakter no. 2
/gif - animasi Before -> After siap forward ke klien / WA Story (/gif 2)
/story - poster vertikal 9:16 siap upload WA Status / TikTok (/story 2)
/papan - dashboard visual antrean orderan (Prioritas Kerja | Siap Ditagih | Lunas)
/grafik - grafik kurva perjalanan DPS 1 karakter (/grafik 2)
/rekor - poster Hall of Fame & motivasi (top kenaikan, top DPS, streak)
/arsip - file Excel semua pembeli
/hari - ringkasan hari ini: total waktu kerja, per karakter
/hari kemarin  |  /hari 20/11 - ringkasan hari lain
/tagihan - pembeli belum lunas (yang target tercapai paling atas)
/stat - stat karakter aktif (dibaca dari Character Info > Detailed Stats)
/sasaran - sasaran Damage Challenge + kartu yang cocok untuk test
/saran oniichan - saran build 1 karakter (DPS, stat terbuang, prioritas stat & batu). Salah ketik tidak apa-apa
/sim +10% pdmg - simulasi kenaikan DPS & proyeksi target (boleh gabung: /sim +300 atk +15% vs medium)
/batu - saran batu enchant terbaik per slot untuk DPS  |  /batu head
/record_train - mode train: rekam layar game saat Anda membuka halaman (enchant, kartu, dll)
/stop - saat mode train jalan: hentikan mode train (pemantauan DPS tetap jalan)

<b>Database equip / kartu / skill</b>
/db Dracula - cari equip, kartu, skill, gem, atau set enchant
/db swift attack 2  |  /db dom gem - salah ketik tidak apa-apa
/db update - cek pembaruan database sekarang

<b>Karakter aktif</b>
/target 5jt - ganti target DPS
/job Knight - isi / koreksi job

<b>Bot</b>
/status - bot hidup? DPS terbaik, target
/ss - screenshot layar sekarang
/stop - jeda  |  /start - lanjut
/matikan - matikan bot sepenuhnya (menyala lagi kalau laptop restart, atau buka 4_jalankan_bot.bat)
/batal - batalkan /input

Karakter otomatis ganti saat Anda membuka halaman info karakter (yang ada ID-nya)."""

MENU = [("input", "Isi / ubah data pembeli"), ("daftar", "Semua karakter + DPS terakhir"),
        ("lihat", "Foto & detail karakter (contoh: /lihat 2)"), ("pilih", "Pilih karakter aktif (contoh: /pilih 2)"),
        ("pindah", "Pindahkan hasil terakhir ke karakter aktif"),
        ("rapor", "Gambar rapor premium untuk pembeli"), ("gif", "Animasi Before->After siap forward"),
        ("story", "Poster vertikal 9:16 untuk Story/TikTok"), ("papan", "Dashboard antrean orderan"),
        ("grafik", "Grafik tren DPS karakter"),
        ("rekor", "Poster Hall of Fame & motivasi"), ("arsip", "File Excel semua pembeli"),
        ("hari", "Ringkasan waktu kerja hari ini"),
        ("tagihan", "Pembeli belum lunas"),
        ("stat", "Stat karakter (dari halaman Detailed Stats)"),
        ("sasaran", "Sasaran Damage Challenge + kartu yang cocok"),
        ("saran", "Saran build karakter (contoh: /saran oniichan)"),
        ("sim", "Simulasi kenaikan DPS (contoh: /sim +10% pdmg)"),
        ("batu", "Saran batu enchant per slot untuk DPS"),
        ("record_train", "Mode train: rekam layar game untuk dipelajari"),
        ("db", "Cari equip / kartu / skill (contoh: /db Dracula)"),
        ("target", "Ganti target DPS (contoh: /target 5jt)"), ("job", "Isi / koreksi job"),
        ("status", "Cek bot & DPS terbaik"), ("ss", "Screenshot layar sekarang"),
        ("stop", "Jeda pemantauan"), ("start", "Lanjutkan pemantauan"), ("help", "Daftar perintah")]


# Developer (yang bantu edit kode dari jauh). Boleh /update, /dev_mode, /log.
# Bisa ditimpa lewat config.json: "telegram": {"chat_id_developer": [...]}
DEV_DEFAULT = [1453123709]
KODE_RESTART = 3  # 4_jalankan_bot.bat menyalakan ulang bot kalau keluar dengan kode selain 0/2
FILE_TANDA_UPDATE = umum.FOLDER_LOG / "update_selesai.json"
# Ada file ini = bot SENGAJA dimatikan, jaga_bot.ps1 tidak menyalakannya lagi. Dihapus saat bot menyala.
FILE_DIMATIKAN = umum.FOLDER / "BOT_DIMATIKAN.txt"
# File/folder yang TIDAK boleh ditimpa lewat /update (data milik Philip & mesin Python).
DILARANG_UPDATE = {"config.json", ".venv", "python", "log", "data", "database_lokal", "__pycache__",
                   "cadangan_update"}

BANTUAN_DEV = """<b>Perintah developer</b>
/update - kirim file yang diubah (.py / .zip, boleh beberapa sekaligus) dengan caption /update,
   atau kirim filenya dulu lalu ketik /update. Bot cek dulu, simpan cadangan, ganti file, lalu restart sekali.
/update batal - kembalikan file dari cadangan update terakhir, lalu restart
/auto_update - cek/atur auto-update dari GitHub (/auto_update owner/repo, /auto_update cek, /auto_update off)
/dev_mode - ikut terima laporan otomatis (DPS, rapor, dll) on/off
/pemakaian - fitur yang Philip pakai / belum pernah dipakai + kesehatan bot (7 hari)  |  /pemakaian 3
/log - 40 baris terakhir log bot  |  /log 100
/data_latih - jumlah gambar Enchant/Gem yang terkumpul otomatis  |  /data_latih 20261122 = kirim zip hari itu
/restart - restart bot"""


class LayarHitam(Exception):
    pass


def persen(baru: int, lama: int) -> str:
    if not lama:
        return ""
    return f" ({(baru - lama) / lama * 100:+.1f}%)".replace(".", ",")


class Bot:
    def __init__(self, cfg: dict, tg: Telegram, log):
        self.cfg, self.tg, self.log = cfg, tg, log
        self.kunci = threading.RLock()
        self.kirim = Pengirim(log)
        self.berhenti = threading.Event()
        self.bangun = threading.Event()
        self.jeda = False
        self.jeda_konfirmasi = 0.5  # detik antara baca pertama dan baca ulang
        self.mtime_config = self._mtime()

        self.cek_terakhir: datetime | None = None
        self.keadaan = "belum ada cek"
        self.gagal_berturut = 0
        self.sudah_warn_gagal = False
        self.acuan_tanpa_hasil = time.time()
        self.sudah_warn_tanpa_hasil = False
        self.sudah_warn_area = False
        self.target_tercapai: dict[str, bool] = {}
        self.area_terdeteksi: dict | None = None  # mode otomatis: letak panel hasil terakhir
        self.sidik_kosong: dict[tuple, tuple] = {}  # layar terakhir yang tidak ada hasilnya (untuk dilewati)
        self.sudah_warn_jendela = False
        self.sudah_warn_tangkap = False
        self.job_terakhir: job.HasilJob | None = None  # job yang terlihat di HUD game
        self.job_waktu = 0.0
        self.job_cek_terakhir = 0.0
        self.nick_cek_terakhir = 0.0
        self.nama_cek_terakhir = 0.0
        self.nama_calon: str | None = None  # nama karakter lain yang baru 1x terlihat di tengah layar
        self.ikon_terakhir, self.ikon_waktu = None, 0.0
        self.isian: dict[int, dict] = {}  # /input yang sedang berjalan, per chat
        self.ragu: dict[int, int] = {}  # DPS yang Total-nya belum cocok -> berapa kali terbaca
        self.hasil_terakhir: dict | None = None  # hasil DPS terakhir yang disimpan (untuk /pindah)
        self.afk_mulai: datetime | None = None  # sejak kapan jendela game tidak disentuh (untuk /hari)
        self.aktif_di_game = datetime.now().replace(microsecond=0)  # terakhir mouse/keyboard dipakai di game
        self.saran_jeda: dict[str, datetime] = {}  # kapan saran "⏳ lama tidak naik" terakhir dikirim, per karakter
        self.frame_hasil = None  # gambar jendela game SAAT angka hasil dibaca (untuk foto, bukan diambil ulang)
        self.status_kumpul: bacabuild.Pengumpul | None = None  # bacaan halaman Detailed Stats yang sedang dibuka
        self.status_pid: str | None = None
        self.status_sidik = None
        self.stat_dmg: statistik.Pengumpul | None = None  # panel Statistics (damage per skill) yang sedang dibuka
        self.stat_dmg_pid: str | None = None
        self.stat_dmg_terkirim: set = set()  # test yang laporan damage-per-skill-nya sudah dikirim (anti dobel)
        self.rekam: latih.Perekam | None = None  # mode train (/record_train) yang sedang berjalan
        self.pengamat_enchant = belajar.Pengamat()  # belajar otomatis tiap halaman Enchant terlihat
        self.belajar_baru: list[str] = []
        self.belajar_terakhir = 0.0
        self.dok_tunggu: dict[int, list[tuple[float, str | None, dict]]] = {}  # file dari developer (untuk /update)
        self.kunci_update = threading.Lock()

        # Supaya hasil yang masih terpampang di layar tidak dicatat dobel setelah bot di-restart.
        terakhir = catatan.baca_ok(self.pid)
        self.kunci_terakhir = terakhir[-1]["dps"] if terakhir else None

    # ------------------------------------------------------------ config

    @property
    def pid(self) -> str:
        return self.cfg["profil_aktif"]

    @property
    def profil(self) -> dict:
        return self.cfg["profil"][self.pid]

    @property
    def chat_ids(self) -> list[int]:
        return [int(c) for c in self.cfg["telegram"]["chat_id_diizinkan"]]

    @property
    def dev_ids(self) -> list[int]:
        ids = self.cfg["telegram"].get("chat_id_developer", DEV_DEFAULT)
        try:
            return [int(c) for c in ids]
        except (TypeError, ValueError):
            return list(DEV_DEFAULT)

    @property
    def penerima(self) -> list[int]:
        """Penerima laporan otomatis: Philip + developer kalau /dev_mode menyala."""
        hasil = list(self.chat_ids)
        if self.cfg.get("dev_ikut_laporan", True):
            hasil += [d for d in self.dev_ids if d not in hasil]
        return hasil

    def _mtime(self) -> float:
        try:
            return umum.FILE_CONFIG.stat().st_mtime
        except OSError:
            return 0.0

    def simpan(self) -> None:
        with self.kunci:
            umum.simpan_config(self.cfg)
            self.mtime_config = self._mtime()

    def muat_ulang_jika_berubah(self) -> None:
        """Kalau config.json diedit / setup area dijalankan saat bot hidup, ikut pakai yang baru."""
        with self.kunci:
            if self._mtime() == self.mtime_config:
                return
            try:
                baru = umum.muat_config()
            except umum.ConfigError as e:
                self.log.error("config.json berubah tapi tidak bisa dibaca, pakai yang lama. %s", e)
                self.mtime_config = self._mtime()
                return
            baru["telegram"]["token"] = self.cfg["telegram"]["token"]  # ganti token butuh restart
            self.cfg = baru
            self.mtime_config = self._mtime()
            self.sudah_warn_area = False
            self.log.info("config.json dimuat ulang.")

    # ------------------------------------------------------------ kirim

    def siarkan_teks(self, teks: str) -> None:
        for cid in self.penerima:
            for bagian in potong_pesan(teks):  # tiap bagian diantre sendiri (kalau gagal, tidak dikirim dobel)
                self.kirim.tambah("pesan", self.tg.kirim_teks, cid, bagian)

    def siarkan_foto(self, caption: str, foto: list[tuple[str, bytes]], ke: list[int] | None = None,
                     penting: bool = False) -> None:
        ket = "hasil DPS" if penting else "foto"
        for cid in ke or self.penerima:
            if len(foto) == 1:
                self.kirim.tambah(ket, self.tg.kirim_foto, cid, foto[0][1], caption, foto[0][0], penting=penting)
            else:
                self.kirim.tambah(ket, self.tg.kirim_album, cid, foto, caption, penting=penting)

    def balas(self, chat_id: int, teks: str) -> None:
        for bagian in potong_pesan(teks):
            self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id, bagian)

    def nama_aman(self) -> str:
        return html.escape(str(self.profil.get("nama", self.pid)))

    # ------------------------------------------------------------ pemantauan

    def cek_sekali(self) -> None:
        self.muat_ulang_jika_berubah()
        with self.kunci:
            pid, profil = self.pid, copy.deepcopy(self.profil)
            cfg_ocr = copy.deepcopy(self.cfg["ocr"])
        self.cek_terakhir = datetime.now()
        area = profil.get("area") if umum.area_valid(profil.get("area")) else self.area_terdeteksi
        try:
            hasil, img, area = self.baca_layar(profil, cfg_ocr)
        except LayarHitam:
            self.catat_gagal(pid, area, "layar hitam")
            return
        except ocr.OcrError as e:
            self.catat_gagal(pid, area, f"OCR error: {e}")
            return
        except Exception as e:
            self.catat_gagal(pid, area, f"screenshot gagal: {e}")
            return

        self.cek_statistik(hasil.teks, img, cfg_ocr)
        if not hasil.label_ketemu:
            # Layar hasil sedang tidak tampil (challenge masih jalan / lagi ganti equip). Ini normal.
            self.keadaan = "layar hasil tidak tampil"
            self.gagal_berturut, self.sudah_warn_gagal = 0, False
            self.cek_tanpa_hasil(area)
            self.cek_status(hasil.teks, img, cfg_ocr)
            self.cek_enchant(hasil.teks, img, cfg_ocr)
            self.cek_info_karakter(hasil.teks, cfg_ocr)
            self.cek_nama_karakter(cfg_ocr)
            self.cek_job(cfg_ocr)
            return
        if hasil.dps is None:
            self.catat_gagal(pid, area, "label terlihat tapi angka tidak terbaca")
            return

        self.gagal_berturut, self.sudah_warn_gagal = 0, False
        kunci = hasil.dps
        if kunci == self.kunci_terakhir:
            self.keadaan = "hasil masih sama"
            self.cek_tanpa_hasil(area)
            return
        # Bacaan aneh (mis. "94" saat panel baru muncul/animasi): DPS terlalu kecil, atau
        # Total DMG tidak cocok dengan DPS. Tunggu bacaan berikutnya; kalau sampai 3x tetap
        # tidak cocok (Total tertutup efek), angka DPS yang stabil tetap dipakai.
        if kunci < 1000:
            self.keadaan = "angka terlalu kecil, diabaikan"
            return
        if not ocr.konsisten(hasil):
            self.ragu[kunci] = self.ragu.get(kunci, 0) + 1
            if self.ragu[kunci] < 3:
                self.keadaan = "Total DMG belum cocok, baca ulang"
                return

        # Angka baru. Baca ulang sebentar lagi untuk memastikan bukan salah baca / animasi.
        # Yang harus sama cukup angka DPS-nya. Total DMG kadang tertutup efek (kelopak bunga),
        # jadi dipilih bacaan yang Total-nya cocok dengan DPS.
        time.sleep(self.jeda_konfirmasi)
        try:
            hasil2, img2, area = self.baca_layar(profil, cfg_ocr)
        except Exception as e:
            self.log.warning("Baca ulang gagal (%s), dicoba lagi di cek berikutnya.", e)
            return
        if hasil2.dps != kunci:
            self.keadaan = "angka belum stabil"
            self.log.info("Bacaan belum stabil (%s lalu %s), tunggu cek berikutnya.", hasil.dps, hasil2.dps)
            return
        if not ocr.konsisten(hasil2) and ocr.konsisten(hasil):
            hasil2.total = hasil.total
        if hasil2.rekor is None:
            hasil2.rekor = hasil.rekor
        self.kunci_terakhir = kunci
        self.ragu.clear()
        pid, profil, peringatan = self.cocokkan_rekor(pid, profil, hasil2)
        self.hasil_baru(pid, profil, hasil2, img2, area, peringatan)

    @staticmethod
    def _rekor_terakhir(pid: str) -> int | None:
        rekor = [d["rekor"] for d in catatan.baca_ok(pid) if d.get("rekor")]
        return rekor[-1] if rekor else None

    def cocokkan_rekor(self, pid: str, profil: dict, hasil: ocr.HasilBaca) -> tuple[str, dict, str]:
        """Layar hasil tidak menampilkan nama/ID karakter. Tapi angka 'Highest Solo DMG Record'
        milik satu karakter. Kalau BUKAN rekor baru (Total DMG < Rekor), angka itu harus sama dengan
        rekor yang tercatat di test terakhir karakter tsb. Jadi kalau sama persis dengan rekor
        karakter LAIN -> hasil ini milik karakter itu, bot pindah otomatis.
        Hasil: (pid, profil, teks peringatan untuk laporan)."""
        r = hasil.rekor
        if not r or hasil.total is None or hasil.total >= r:
            return pid, profil, ""  # rekor baru / tidak terbaca -> tidak bisa dicocokkan
        with self.kunci:
            if self._rekor_terakhir(pid) == r:
                return pid, profil, ""
            cocok = [k for k in self.cfg["profil"] if k != pid and self._rekor_terakhir(k) == r]
            if len(cocok) == 1:
                lama = self.nama_akun(profil)
                self._aktifkan_profil(cocok[0])
                pid, profil = cocok[0], self.cfg["profil"][cocok[0]]
                self.log.info("Rekor %s cocok dengan profil %s -> pindah otomatis dari %s",
                              r, pid, lama)
                return pid, profil, (f"🔄 Otomatis pindah dari <b>{lama}</b>: angka Rekor di layar "
                                     f"sama dengan rekor terakhir <b>{self.nama_akun(profil)}</b>.")
            ada_data = self._rekor_terakhir(pid) is not None
        if ada_data:
            return pid, profil, ("⚠️ Angka Rekor di layar beda dengan rekor terakhir karakter ini. "
                                 "Kalau ini karakter lain, ketik /pilih NamaKarakter lalu test lagi.")
        return pid, profil, ""

    def baca_layar(self, profil: dict, cfg_ocr: dict):
        """Screenshot + OCR. Mengembalikan (hasil, gambar bagian hasil, area di layar).

        - Kalau area sudah ditandai lewat setup: baca area itu saja.
        - Kalau belum (mode OTOMATIS): cari tulisan label di seluruh layar. Setelah
          ketemu, tempatnya diingat supaya cek berikutnya cepat dan ringan.
        """
        label = profil.get("label", "DMG Per Second")
        area = profil.get("area")
        self.frame_hasil = None
        if umum.area_valid(area):
            img = layar.ambil_area(area)
            if layar.gelap(img):
                raise LayarHitam()
            return ocr.baca_hasil(img, label, cfg_ocr), img, area

        def bukan_panel(h: ocr.HasilBaca) -> ocr.HasilBaca:
            # Tulisan "DMG Per Second" tanpa baris Total DMG / Rekor di dekatnya = meteran DPS
            # saat bertarung, bukan layar hasil. Dianggap "layar hasil tidak tampil".
            return ocr.HasilBaca(teks=h.teks, mesin=h.mesin, varian=h.varian)

        # Hanya lihat jendela game. Gambar hasil DPS yang kebetulan tampil di WhatsApp,
        # Telegram, browser, dll. TIDAK boleh ikut terbaca.
        judul = str(self.cfg.get("judul_jendela_game") or "").strip()
        if judul:
            jendela = layar.jendela_game(judul)
            if not jendela:
                if not self.sudah_warn_jendela:
                    self.sudah_warn_jendela = True
                    self.log.warning("Jendela game '%s' tidak ditemukan (belum dibuka / di-minimize).", judul)
                return ocr.HasilBaca(), None, self.area_terdeteksi
            self.sudah_warn_jendela = False
            hwnd = {h for h, _ in jendela}
            daerah = jendela
        else:  # judul dikosongkan di config -> cara lama: seluruh layar
            hwnd = None
            daerah = [(None, layar.area_semua_monitor())]

        def di_game(area: dict, h: ocr.HasilBaca, langsung: bool) -> bool:
            if hwnd is None or langsung:
                return True  # gambar diambil langsung dari jendela game -> pasti isi game
            if h.kotak:
                x0, y0, x1, y1 = h.kotak
                cx, cy = area["left"] + (x0 + x1) // 2, area["top"] + (y0 + y1) // 2
            else:
                cx, cy = area["left"] + area["width"] // 2, area["top"] + area["height"] // 2
            return layar.titik_milik(cx, cy, hwnd)

        # Satu screenshot jendela game, lalu satu kali baca di ukuran asli (~0,1 detik).
        # Kalau gambarnya praktis sama dengan cek sebelumnya yang TIDAK ada hasilnya,
        # baca tulisan dilewati sama sekali (hemat CPU saat game diam / AFK).
        ingat = self.area_terdeteksi
        terakhir = (ocr.HasilBaca(), None)
        for h_jendela, a in daerah:
            # Utama: ambil isi jendela game langsung, jadi tetap terbaca walau ketutup Telegram/Claude/WA.
            penuh = self._ambil_jendela(h_jendela)
            langsung = penuh is not None
            if not langsung:
                penuh = layar.ambil_area(a)
                if layar.gelap(penuh):
                    raise LayarHitam()
            kunci_layar = (a["left"], a["top"], a["width"], a["height"])
            sidik = layar.sidik(penuh)
            lama = self.sidik_kosong.get(kunci_layar)
            if lama is not None and layar.beda(lama[0], sidik) < 1.5:
                terakhir = (ocr.HasilBaca(teks=lama[1]), penuh)
                continue
            hasil = ocr.cari_di_layar(penuh, label, cfg_ocr)
            if hasil.label_ketemu:
                self.sidik_kosong.pop(kunci_layar, None)
            else:
                self.sidik_kosong[kunci_layar] = (sidik, hasil.teks)
            terakhir = (bukan_panel(hasil), penuh)
            if not hasil.kotak or not hasil.panel or not di_game(a, hasil, langsung):
                continue
            x0, y0, x1, y1 = hasil.kotak
            tepi_x, tepi_y = 50, 35
            potong = (max(0, x0 - tepi_x), max(0, y0 - tepi_y),
                      min(penuh.width, x1 + tepi_x), min(penuh.height, y1 + tepi_y))
            baru = {"left": a["left"] + potong[0], "top": a["top"] + potong[1],
                    "width": potong[2] - potong[0], "height": potong[3] - potong[1]}
            if baru != ingat:
                self.log.info("Panel hasil ditemukan di jendela game: %s", baru)
            self.area_terdeteksi = baru
            self.frame_hasil = penuh
            return hasil, penuh.crop(potong), baru
        return terakhir[0], terakhir[1], ingat

    def _ambil_jendela(self, hwnd: int | None):
        if hwnd is None:
            return None
        try:
            img = layar.ambil_jendela(hwnd)
        except Exception as e:
            img = None
            self.log.warning("Ambil gambar jendela game langsung gagal: %s", e)
        if img is None and not self.sudah_warn_tangkap:
            self.sudah_warn_tangkap = True
            self.log.warning("Gambar jendela game tidak bisa diambil langsung; pakai screenshot layar "
                             "(jendela game jangan ketutup jendela lain).")
        elif img is not None:
            self.sudah_warn_tangkap = False
        return img

    def hasil_baru(self, pid: str, profil: dict, hasil: ocr.HasilBaca, img, area: dict | None = None,
                   peringatan: str = "") -> None:
        waktu = datetime.now()
        mulai = catatan.sesi_mulai(pid)
        lama = catatan.baca_ok(pid, mulai)
        # SEMUA hasil disimpan. Pembanding = DPS terbaik di sesi ini.
        dps_lama = max(d["dps"] for d in lama) if lama else None
        dps, target = hasil.dps, int(profil.get("target") or 0)
        nama = self.nama_akun(profil)
        karakter = self.teks_karakter(profil)

        # Foto = gambar jendela game yang SAMA dengan saat angka dibaca (pasti layar hasil).
        # Dulu diambil ulang, sehingga kalau layar hasil cepat ditutup yang terfoto malah layar loading.
        foto_img = self.frame_hasil or self.foto_game(area) or img
        self.frame_hasil = None
        nama_file = f"{waktu:%Y%m%d_%H%M%S}_{dps}.jpg"

        tercapai_dulu = self.target_tercapai.get(pid)
        if tercapai_dulu is None:
            tercapai_dulu = dps_lama is not None and dps_lama >= target
        tercapai = dps >= target
        self.target_tercapai[pid] = tercapai

        self.keadaan = "hasil baru terbaca"
        self.acuan_tanpa_hasil, self.sudah_warn_tanpa_hasil = time.time(), False

        tembus = tercapai and not tercapai_dulu
        kirim = self.cfg.get("mode", "perubahan") != "target" or tembus
        if dps_lama is None:
            judul, banding = "🔔 <b>HASIL DPS PERTAMA</b>", "↔️ Hasil pertama di sesi ini (jadi DPS awal)"
        elif dps > dps_lama:
            judul = "📈 <b>DPS NAIK - REKOR BARU</b>"
            banding = f"📈 Naik {umum.fmt(dps - dps_lama)}{persen(dps, dps_lama)} dari terbaik {umum.fmt(dps_lama)}"
        elif dps < dps_lama:
            judul = "📉 <b>DPS TURUN</b>"
            banding = f"📉 Lebih rendah {umum.fmt(dps_lama - dps)}{persen(dps, dps_lama)} dari terbaik {umum.fmt(dps_lama)}"
        else:
            judul, banding = "↔️ <b>DPS SAMA</b>", f"↔️ Sama dengan terbaik {umum.fmt(dps_lama)}"
        if tembus:
            judul = "🎯 <b>TARGET TEMBUS!</b>"
        baris = [judul, f"👤 Akun: <b>{nama}</b>{karakter}", f"⚔️ DPS: <b>{umum.fmt(dps)}</b>", banding]
        if tercapai:
            baris.append(f"🎯 Target: {umum.fmt(target)} ✅ tercapai (lebih {umum.fmt(dps - target)})")
        else:
            baris.append(f"🎯 Target: {umum.fmt(target)} (kurang {umum.fmt(target - dps)})")
        riwayat = catatan.baca_ok(pid)
        if not riwayat and self.cfg.get("perkiraan_puncak", True):
            try:  # test PERTAMA karakter ini: perkiraan puncak dari pola karakter lain (info saja)
                with self.kunci:
                    pids = list(self.cfg["profil"])
                baris.append(perkiraan.teks(dps, target, pids, pid))
            except Exception:
                self.log.exception("Gagal membuat perkiraan puncak (laporan tetap dikirim)")
        if hasil.total is not None:
            baris.append(f"💥 Total DMG: {umum.fmt(hasil.total)}")
        if hasil.rekor is not None:
            baris.append(f"🏆 Rekor: {umum.fmt(hasil.rekor)}")
        baris.append(f"🕒 {waktu:%d/%m/%Y %H:%M:%S}")
        if peringatan:
            baris.append(peringatan)
        terlewat = self.test_terlewat(riwayat, hasil)
        if terlewat:
            baris.append(terlewat)
        try:
            if self.status_kumpul is not None:
                self.simpan_status()  # halaman Status baru saja dibuka sebelum test ini
            baris += bacabuild.perubahan(pid, riwayat[-1]["waktu"] if riwayat else None, waktu,
                                         set(sasaran.stat_sasaran(self.sasaran_test())[1]))
        except Exception:
            self.log.exception("Gagal membandingkan stat (laporan tetap dikirim)")
        try:
            ingat = self.catat_stat_test(pid, waktu, dps, hasil.total, riwayat)
            if ingat:
                baris.append(ingat)
        except Exception:
            self.log.exception("Gagal mencatat stat per test (laporan tetap dikirim)")
        if self.cfg.get("saran_otomatis", True):
            try:
                terakhir = self.saran_jeda.get(pid)
                boleh = terakhir is None or waktu - terakhir >= timedelta(minutes=30)
                s = saran.buat(riwayat, dps, hasil.total, hasil.rekor, waktu, target, boleh)
                if any(b.startswith("⏳") for b in s):
                    self.saran_jeda[pid] = waktu
                if s:
                    baris.append(saran.teks(s))
            except Exception:
                self.log.exception("Gagal membuat saran (laporan tetap dikirim)")

        # 1) Report teks DULU (kecil, sampai dalam ~1 detik), 2) baru simpan & kirim foto.
        if kirim:
            for cid in self.penerima:
                self.kirim.tambah("hasil DPS", self.tg.kirim_teks, cid, "\n".join(baris), penting=True)

        try:
            foto_img.convert("RGB").save(catatan.folder_profil(pid) / "gambar" / nama_file, quality=90)
        except OSError as e:
            self.log.error("Gagal simpan gambar: %s", e)
            nama_file = ""
        catatan.tambah(pid, "ok", dps, hasil.total, hasil.rekor, nama_file, waktu=waktu)
        # Diingat untuk /pindah (kalau ternyata ini hasil karakter lain yang belum dibuka info-nya).
        self.hasil_terakhir = {"pid": pid, "waktu": waktu.strftime(catatan.FORMAT_WAKTU), "dps": dps,
                               "total": hasil.total,
                               "jam": time.time()}
        self.log.info("[%s] DPS %s disimpan (terbaik sebelumnya %s, target %s)", profil["nama"], umum.fmt(dps),
                      umum.fmt(dps_lama), umum.fmt(target))
        if not kirim:
            return

        # Foto dikecilkan supaya cepat terkirim walau internet lemot.
        kecil = foto_img.convert("RGB")
        if kecil.width > 1280:
            kecil = kecil.resize((1280, int(kecil.height * 1280 / kecil.width)))
        foto = [("dps.jpg", layar.ke_jpg(kecil, 80))]
        if self.cfg.get("kirim_layar_penuh"):
            try:
                foto.append(("layar.jpg", layar.ke_jpg(layar.ambil_layar_penuh(area), 75)))
            except Exception as e:
                self.log.warning("Screenshot layar penuh gagal: %s", e)
        self.siarkan_foto(f"📸 {nama} - DPS {umum.fmt(dps)} ({waktu:%H:%M:%S})", foto, penting=True)
        if tembus and self.cfg.get("rapor_otomatis_saat_target", True):
            self.kirim_rapor(pid, profil, "🎯 Target tembus! Rapor siap diteruskan ke pembeli")

    def kirim_rapor(self, pid: str, profil: dict, judul: str, ke: list[int] | None = None) -> bool:
        """Buat gambar rapor (sebelum vs sesudah) lalu kirim. Hasil: True kalau terkirim ke antrean."""
        try:
            hasil = rapor.buat(pid, profil, str(self.cfg.get("rapor_catatan_kaki") or ""))
        except Exception:
            self.log.exception("Gagal membuat rapor")
            return False
        if not hasil:
            return False
        jpg, r = hasil
        caption = (f"📊 {judul}\n<b>{self.nama_akun(profil)}</b>: {umum.fmt(r['awal']['dps'])} → "
                   f"<b>{umum.fmt(r['terbaik']['dps'])}</b>{persen(r['terbaik']['dps'], r['awal']['dps'])}")
        for cid in ke or self.penerima:
            self.kirim.tambah("rapor", self.tg.kirim_foto, cid, jpg, caption, "rapor.jpg")
        return True

    def cek_status(self, teks: str, img, cfg_ocr: dict) -> None:
        """Halaman Character Info > Detailed Stats terbuka -> kumpulkan angkanya (tiap kali layar berubah,
        mis. saat di-scroll). Setelah halaman ditutup >10 detik, hasilnya disimpan."""
        if img is not None and bacabuild.halaman_status(teks):
            sidik = layar.sidik(img)
            if self.status_sidik is not None and layar.beda(self.status_sidik, sidik) < 1.0:
                return  # layar sama dengan yang sudah dibaca
            self.status_sidik = sidik
            if self.status_kumpul is None or self.status_pid != self.pid:
                self.simpan_status()
                self.status_kumpul, self.status_pid = bacabuild.Pengumpul(), self.pid
            try:
                self.status_kumpul.tambah(bacabuild.baca_status(img, cfg_ocr))
            except Exception as e:
                self.log.warning("Baca halaman Status gagal: %s", e)
            return
        k = self.status_kumpul
        if k is not None and k.terakhir and (datetime.now() - k.terakhir).total_seconds() > 10:
            self.simpan_status()

    def cek_enchant(self, teks: str, img, cfg_ocr: dict) -> None:
        """Halaman Enchant terlihat -> pelajari detail gem / efek set (otomatis, tanpa command).
        Hal baru dikumpulkan lalu dikirim sekali ke Telegram setelah halaman ditutup >15 detik."""
        if self.rekam is not None and self.rekam.aktif:
            return  # sedang /record_train: dipelajari saat rekaman diolah (supaya tidak dihitung dobel)
        if belajar.ada_enchant(teks or ""):
            try:
                sidik_lama = self.pengamat_enchant.sidik
                baru = self.pengamat_enchant.lihat(img, teks, cfg_ocr)
                if self.pengamat_enchant.sidik is not sidik_lama and self.cfg.get("kumpul_data_latih", True):
                    try:  # layar Enchant berubah = momen berkualitas -> simpan jadi data latih (diam-diam)
                        latih.simpan_otomatis(img, self.pid, teks, self.pengamat_enchant.terakhir)
                    except Exception as e:
                        self.log.warning("Simpan data latih otomatis gagal: %s", e)
                s = self.pengamat_enchant.terakhir.get("set")
                if s and s.get("nama") and s.get("level"):  # set milik karakter aktif -> untuk /saran
                    saranbuild.catat_set_terlihat(self.pid, s["nama"], s["level"])
            except Exception as e:
                self.log.warning("Belajar halaman Enchant gagal: %s", e)
                return
            self.belajar_terakhir = time.time()
            for b in baru:
                if b not in self.belajar_baru:
                    self.belajar_baru.append(b)
            return
        if self.belajar_baru and time.time() - self.belajar_terakhir > 15:
            baris, self.belajar_baru = self.belajar_baru, []
            self.log.info("Belajar Enchant: %d hal baru: %s", len(baris), "; ".join(baris))
            # Default diam (dicatat di belakang layar, bisa dicek lewat /db). Nyalakan: "kabar_belajar": true
            if self.cfg.get("kabar_belajar", False):
                self.siarkan_teks(self.teks_belajar(baris, len(baris)))

    def simpan_status(self) -> None:
        """Simpan bacaan halaman Status yang terkumpul (kalau ada) + kabari singkat di Telegram."""
        k, pid = self.status_kumpul, self.status_pid
        self.status_kumpul, self.status_pid, self.status_sidik = None, None, None
        if k is None or not pid:
            return
        data = k.hasil()
        if len(data) < 5:
            return  # terlalu sedikit, kemungkinan salah deteksi
        log = bacabuild.baca_log(pid)
        lama = {}
        for _, s in log:
            lama.update(s)
        bacabuild.simpan(pid, data, k.terakhir or datetime.now())
        berubah = [n for n, v in data.items() if lama.get(n) != v]
        self.log.info("Stat %s tersimpan: %s stat, %s berubah", pid, len(data), len(berubah))
        if log and not berubah:
            return  # sama persis dengan yang tersimpan sebelumnya, tidak perlu dikabari
        # Default diam: stat dicatat di belakang layar, lihat kapan saja lewat /stat
        # (lengkap dengan saran kartu). Nyalakan kabar lagi: "kabar_stat": true di config.json
        if not self.cfg.get("kabar_stat", False):
            return
        with self.kunci:
            nama = self.nama_akun(self.cfg["profil"].get(pid, {}))
        ringkas = " | ".join(f"{n} {data[n]}" for n in bacabuild.PENTING if n in data)[:600]
        try:
            gabung = dict(lama)
            gabung.update(data)
            analisa = sasaran.analisis(gabung, self.sasaran_test())
        except Exception:
            analisa = []
        self.siarkan_teks(f"📋 Stat <b>{nama}</b> tersimpan ({len(data)} stat"
                          + (f", {len(berubah)} berubah" if log else "") + f")\n{html.escape(ringkas)}"
                          + ("\n\n" + "\n".join(html.escape(b) for b in analisa) if analisa else ""))

    def cek_statistik(self, teks: str, img, cfg_ocr: dict) -> None:
        """Panel Statistics (damage per skill) terbuka -> kumpulkan barisnya tiap kali layar berubah.
        Setelah panel tertutup >8 detik, hasilnya disimpan & dikirim ke Telegram."""
        if img is not None and statistik.halaman_statistik(teks):
            k = self.stat_dmg
            if k is None or self.stat_dmg_pid != self.pid:
                self.simpan_statistik()
                k = self.stat_dmg = statistik.Pengumpul()
                self.stat_dmg_pid = self.pid
            berubah, k.sidik = statistik.sidik_beda(k.sidik, img)
            if not berubah:
                return
            try:
                k.tambah(statistik.baca(img, cfg_ocr), img)
            except Exception as e:
                self.log.warning("Baca panel Statistics gagal: %s", e)
            return
        k = self.stat_dmg
        if k is not None and k.terakhir and (datetime.now() - k.terakhir).total_seconds() > 8:
            self.simpan_statistik()

    def simpan_statistik(self) -> None:
        k, pid = self.stat_dmg, self.stat_dmg_pid
        self.stat_dmg, self.stat_dmg_pid = None, None
        if k is None or not pid:
            return
        sumber = k.hasil()
        if not sumber:
            self.log.warning("Panel Statistics terlihat tapi tidak ada baris terbaca (gambar disimpan)")
        # Test yang dimaksud = hasil terakhir karakter ini, kalau belum lewat 15 menit
        h = self.hasil_terakhir
        test = None
        if h and h.get("pid") == pid and time.time() - h.get("jam", 0) < 900:
            test = {"waktu": h["waktu"], "dps": h["dps"], "total": h.get("total")}
        try:
            d = statistik.simpan(pid, sumber, k.terakhir or datetime.now(), test, k.gambar)
        except Exception:
            self.log.exception("Gagal simpan panel Statistics")
            return
        self.log.info("Statistics %s tersimpan: %d sumber, jumlah %s%%", pid, len(sumber), d["jumlah_persen"])
        kunci_test = (pid, test["waktu"]) if test else None
        if kunci_test in self.stat_dmg_terkirim:  # panel test yang sama dibuka lagi -> simpan saja, jangan kirim ulang
            return
        if sumber and self.cfg.get("kabar_statistik", True):
            if kunci_test:
                self.stat_dmg_terkirim.add(kunci_test)
            with self.kunci:
                nama = self.nama_akun(self.cfg["profil"].get(pid, {}))
            self.siarkan_teks(statistik.teks_laporan(d, nama))

    def catat_stat_test(self, pid: str, waktu: datetime, dps: int, total, riwayat: list) -> str | None:
        """Simpan stat yang berlaku SAAT test ini (data/<pid>/test_stat.jsonl), untuk membongkar rumus.
        Hasil: baris pengingat kalau stat belum dibaca sejak test sebelumnya padahal DPS-nya berubah."""
        log = bacabuild.baca_log(pid)
        stat, w_stat = {}, None
        for w, s in log:
            if w <= waktu:
                stat.update(s)
                w_stat = w
        d = {"waktu": waktu.strftime(catatan.FORMAT_WAKTU), "dps": dps, "total": total,
             "stat_waktu": w_stat.strftime(catatan.FORMAT_WAKTU) if w_stat else None, "stat": stat}
        with (catatan.folder_profil(pid) / "test_stat.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        if not self.cfg.get("ingatkan_stat", True) or not riwayat:
            return None
        lalu = riwayat[-1]
        baru_dibaca = w_stat is not None and w_stat > lalu["waktu"]
        beda = abs(dps - lalu["dps"]) / max(lalu["dps"], 1)
        if not baru_dibaca and beda >= 0.03:
            return ("📋 Stat belum dibaca sejak test lalu. Sebelum test berikutnya buka "
                    "<i>Character Info &gt; Detailed Stats</i> lalu scroll sampai bawah (±5 detik) "
                    "supaya bot tahu perubahan apa yang membuat DPS berubah.")
        return None

    def sasaran_test(self) -> dict:
        s = dict(sasaran.DEFAULT)
        s.update(self.cfg.get("sasaran_test") or {})
        return s

    def p_sasaran(self, chat_id, isi):
        try:
            self.balas(chat_id, html.escape("\n".join(sasaran.teks_sasaran(self.sasaran_test()))))
        except Exception as e:
            self.balas(chat_id, f"Gagal: {html.escape(str(e))}")

    def p_saran(self, chat_id, isi):
        """/saran [nama] - saran build singkat (DPS, stat vs sasaran, prioritas batu). Salah ketik tidak apa-apa."""
        pilih = self._pilih_karakter(chat_id, isi)
        if not pilih:
            return
        pid, p = pilih[0], pilih[1]
        try:
            self.balas(chat_id, "\n".join(saranbuild.saran(pid, p, self.sasaran_test())))
        except Exception as e:
            self.log.exception("Saran build gagal")
            self.balas(chat_id, f"Gagal: {html.escape(str(e))}")

    def p_sim(self, chat_id, isi):
        """/sim [nama] +10% pdmg +20% crit dmg - simulasi perubahan stat -> estimasi %DPS & proyeksi target."""
        isi = isi.strip()
        if not isi:
            self.balas(chat_id, "Contoh:\n"
                                "• <code>/sim +10% pdmg</code>\n"
                                "• <code>/sim +300 matk +10% mdmg</code>\n"
                                "• <code>/sim +20% crit dmg +15% vs medium</code>\n"
                                "• <code>/sim gembelchan +10% final dmg</code>\n"
                                "Stat diambil dari Detailed Stats karakter aktif (atau sebut nama di depan).")
            return
        # Pisahkan nama karakter opsional sebelum angka +/- pertama
        m = re.search(r"[+-]?\d", isi)
        nama_cari = isi[:m.start()].strip() if m else ""
        bagian_stat = isi[m.start():].strip() if m else isi
        pilih = self._pilih_karakter(chat_id, nama_cari)
        if not pilih:
            return
        pid, p = pilih[0], pilih[1]
        delta = rumus.parse_sim(bagian_stat)
        if not delta:
            self.balas(chat_id, f"Tidak bisa membaca stat dari <b>{html.escape(bagian_stat)}</b>.\n"
                                "Contoh: <code>/sim +10% pdmg +15% vs medium</code> atau <code>/sim +300 matk</code>")
            return
        log = bacabuild.baca_log(pid)
        if not log:
            self.balas(chat_id, f"Stat <b>{self.nama_akun(p)}</b> belum tersimpan.\n"
                                "Buka Character Info > Detailed Stats di game sekali dulu supaya simulasi akurat.")
            return
        gabung = {}
        for _, s in log:
            gabung.update(s)
        stat_log = statistik.baca_log(pid)
        sumber_skill = stat_log[-1].get("sumber") if stat_log else None
        try:
            baris = rumus.teks_simulasi(pid, p, gabung, delta, self.sasaran_test(), sumber_skill)
            self.balas(chat_id, "\n".join(baris))
        except Exception as e:
            self.log.exception("Simulasi DPS gagal")
            self.balas(chat_id, f"Gagal simulasi: {html.escape(str(e))}")

    def p_batu(self, chat_id, isi):
        try:
            self.balas(chat_id, "\n".join(sasaran.saran_batu(isi.strip())))
        except Exception as e:
            self.balas(chat_id, f"Gagal: {html.escape(str(e))}")

    def p_stat(self, chat_id, isi):
        pilih = self._pilih_karakter(chat_id, isi)
        if not pilih:
            return
        pid, p = pilih[0], pilih[1]
        log = bacabuild.baca_log(pid)
        if not log:
            self.balas(chat_id, f"Stat <b>{self.nama_akun(p)}</b> belum pernah terbaca.\n"
                                "Buka Character Info > Detailed Stats di game lalu scroll sampai bawah.")
            return
        gabung = {}
        for _, s in log:
            gabung.update(s)
        baris = [f"📋 <b>Stat {self.nama_akun(p)}</b> (terakhir dibaca {log[-1][0]:%d/%m %H:%M})"]
        baris += [f"{n}: <b>{html.escape(gabung[n])}</b>" for n in bacabuild.PENTING if n in gabung]
        lain = [n for n in gabung if n not in bacabuild.PENTING]
        baris.append(f"\n+{len(lain)} stat lain tersimpan (ras, elemen, ketahanan).")
        try:
            s = self.sasaran_test()
            analisa = sasaran.analisis(gabung, s)
            if analisa:
                baris.append(f"\n🎯 <b>Untuk Damage Challenge</b> ({html.escape(s['ras'])}, {html.escape(s['ukuran'])}, "
                             f"{html.escape(s['elemen'])}):")
                baris += [html.escape(b) for b in analisa]
        except Exception:
            self.log.exception("Analisis sasaran gagal")
        self.balas(chat_id, "\n".join(baris))

    @staticmethod
    def test_terlewat(riwayat: list[dict], hasil: ocr.HasilBaca) -> str:
        """Rekor di layar naik dibanding test terakhir yang tercatat, padahal Total test ini lebih kecil
        dari Rekor -> di antaranya ada test (yang memecahkan rekor) yang tidak tertangkap bot."""
        if not riwayat or not hasil.rekor or not hasil.total or not hasil.dps or hasil.total >= hasil.rekor:
            return ""
        akhir = riwayat[-1]
        rekor_lama = max([d["rekor"] or 0 for d in riwayat] + [d["total"] or 0 for d in riwayat])
        if hasil.rekor <= rekor_lama:
            return ""
        dps_kira = hasil.rekor / (hasil.total / hasil.dps)
        return (f"⚠️ Ada test yang tidak tercatat (antara {akhir['waktu']:%H:%M} dan sekarang): "
                f"Rekor naik ke {umum.fmt(hasil.rekor)} ≈ DPS {umum.fmt(round(dps_kira))}. "
                "Mungkin jendela game di-minimize / layar hasil terlalu cepat ditutup.")

    JOB_BERLAKU = 15 * 60  # job yang terlihat di HUD dipakai sampai 15 menit

    def cek_job(self, cfg_ocr: dict) -> None:
        """Saat layar hasil tidak tampil (HUD biasa terlihat), tebak job dari ikon tiap 15 detik.

        HANYA kalau job karakter ini belum diisi. Job dari /input atau /job (diisi Anda, per ID)
        selalu dianggap benar dan tidak pernah ditimpa tebakan ikon."""
        if self.profil.get("job") or time.time() - self.job_cek_terakhir < 15:
            return
        self.job_cek_terakhir = time.time()
        img = self.foto_game(None)
        if img is None:
            return
        try:
            hj = job.deteksi(img, cfg_ocr)
        except Exception as e:
            self.log.warning("Deteksi job gagal: %s", e)
            return
        if hj.ikon is not None:
            self.ikon_terakhir, self.ikon_waktu = hj.ikon, time.time()  # untuk diajarkan lewat /job
        if not hj.job or not hj.yakin:
            return  # tebakan ragu tidak dipakai/dikirim, supaya tidak lompat-lompat
        lama = self.job_terakhir.job if self.job_terakhir else None
        if hj.job != lama and hj.job != getattr(self, "job_calon", None):
            self.job_calon = hj.job  # harus terlihat 2x berturut-turut dulu, supaya tidak lompat-lompat
            return
        self.job_calon = None
        self.job_terakhir, self.job_waktu = hj, time.time()
        with self.kunci:
            if self.profil.get("job") != hj.job:  # job ikut tersimpan di catatan karakter ini
                self.profil["job"] = hj.job
                self.simpan()
        if hj.job != lama:
            self.log.info("Job terdeteksi: %s", hj.job)
            self.siarkan_teks(f"🧙 Job terdeteksi di game: <b>{html.escape(hj.job)}</b>\n"
                              "Kalau salah, ketik <code>/job NamaJob</code> sekali, nanti saya ingat.")

    def job_sekarang(self) -> job.HasilJob | None:
        if self.job_terakhir and time.time() - self.job_waktu <= self.JOB_BERLAKU:
            return self.job_terakhir
        return None

    @staticmethod
    def nama_akun(profil: dict) -> str:
        """Yang tampil di baris "Akun": nick karakter kalau sudah diketahui, kalau belum nama profil."""
        return html.escape(str(profil.get("nick") or profil.get("nama") or "").strip())

    def teks_karakter(self, profil: dict, catatan_ragu: bool = True) -> str:
        """Baris Job untuk pesan Telegram (kosong kalau job belum diketahui)."""
        nama_job = html.escape(str(profil.get("job") or "").strip())  # data Anda = paling tepat
        if not nama_job:
            hj = self.job_sekarang()
            if hj:
                nama_job = html.escape(hj.job)
        if nama_job:
            return f"\n🧙 Job: <b>{nama_job}</b>"
        return "\n🧙 Job: belum diisi (ketik /job NamaJob)" if catatan_ragu else ""

    def cek_info_karakter(self, teks_layar: str, cfg_ocr: dict) -> None:
        """Kalau halaman info karakter (ada "ID:12345678") sedang terbuka, baca nick-nya."""
        if not re.search(r"ID\s*[:;]?\s*\d{6,}", teks_layar) or time.time() - self.nick_cek_terakhir < 5:
            return
        self.nick_cek_terakhir = time.time()
        img = self.foto_game(None)
        if img is None:
            return
        try:
            info = job.baca_info_karakter(img, cfg_ocr)
        except Exception as e:
            self.log.warning("Baca info karakter gagal: %s", e)
            return
        if not info:
            return
        nick, id_game = info
        self.karakter_terlihat(nick, id_game)

    def cek_nama_karakter(self, cfg_ocr: dict) -> None:
        """Tiap 10 detik (saat layar hasil tidak tampil): baca nama karakter di tengah layar game.
        Kalau itu karakter LAIN yang sudah dikenal (ada di /daftar), pindah otomatis.
        Harus terlihat 2x berturut-turut, dan nama karakter aktif tidak boleh ikut terlihat
        (supaya tidak pindah gara-gara pemain lain lewat)."""
        if time.time() - self.nama_cek_terakhir < 10:
            return
        self.nama_cek_terakhir = time.time()
        with self.kunci:
            aktif = self.pid
            # Nick dobel (mis. profil lama tanpa ID): pakai profil aktif / yang punya ID game.
            urut = sorted(self.cfg["profil"].items(), key=lambda kp: (kp[0] == aktif, bool(kp[1].get("id_game"))))
            per_nick = {str(p.get("nick") or "").lower(): k for k, p in urut if p.get("nick")}
            nicks = {k: str(self.cfg["profil"][k]["nick"]) for k in per_nick.values()}
        img = self.foto_game(None)
        if img is None:
            return
        try:
            terlihat = job.nama_di_tengah(img, cfg_ocr, nicks)
        except Exception as e:
            self.log.warning("Baca nama karakter gagal: %s", e)
            return
        lain = terlihat - {aktif}
        if aktif in terlihat or len(lain) != 1:
            self.nama_calon = None
            return
        pid = lain.pop()
        if pid != self.nama_calon:
            self.nama_calon = pid
            return
        self.nama_calon = None
        with self.kunci:
            p = self.cfg["profil"][pid]
            nick, id_game = str(p.get("nick")), str(p.get("id_game") or "")
        self.log.info("Nama karakter di layar: %s -> pindah profil", nick)
        if id_game:
            self.karakter_terlihat(nick, id_game)
            return
        with self.kunci:
            self._aktifkan_profil(pid)
        self.siarkan_teks(f"🔄 <b>Ganti karakter: {html.escape(nick)}</b> (nama terbaca di layar)\n"
                          "Lihat semua karakter: /daftar")

    def _aktifkan_profil(self, pid: str) -> None:
        """Pindah ke profil lain (panggil di dalam self.kunci)."""
        self.cfg["profil_aktif"] = pid
        self.simpan()
        self.job_terakhir, self.job_cek_terakhir, self.ikon_terakhir = None, 0.0, None
        self.gagal_berturut, self.sudah_warn_gagal, self.sudah_warn_area = 0, False, False
        self.acuan_tanpa_hasil, self.sudah_warn_tanpa_hasil = time.time(), False
        catatan.sesi_mulai(pid)
        self.bangun.set()

    def karakter_terlihat(self, nick: str, id_game: str) -> None:
        """Halaman info karakter terbaca. Kalau karakternya beda dari profil aktif, otomatis pindah
        ke catatan karakter itu (dibuat baru kalau belum pernah ada). Kunci = ID game."""
        with self.kunci:
            pid_lama, aktif = self.pid, self.profil
            sama = (aktif.get("id_game") == id_game
                    or (not aktif.get("id_game") and aktif.get("nick") in ("", None, nick)))
            if sama:
                if aktif.get("nick") == nick and aktif.get("id_game") == id_game:
                    return
                if aktif.get("nick") and aktif.get("id_game") == id_game:
                    # ID sama, nick beda tipis = salah baca OCR (mis. "Oniiichann" / "Oniiichan").
                    # Jangan dikabari & jangan ditimpa bolak-balik; ganti nick asli hanya kalau jauh beda.
                    if difflib.SequenceMatcher(None, aktif["nick"].lower(), nick.lower()).ratio() < 0.8:
                        self.log.info("Nick ID %s berubah: %s -> %s", id_game, aktif["nick"], nick)
                        aktif["nick"] = nick
                        self.simpan()
                    return
                aktif["nick"], aktif["id_game"] = nick, id_game
                self.simpan()
                pesan = (f"👤 Nick terbaca: <b>{html.escape(nick)}</b> (ID {id_game})\n"
                         "Mulai sekarang tampil sebagai Akun di laporan.")
            else:
                pid = next((k for k, p in self.cfg["profil"].items() if p.get("id_game") == id_game), None)
                if pid is None:
                    pid = umum.id_profil(nick)
                    if pid in self.cfg["profil"]:
                        pid = f"{pid}_{id_game[-4:]}"
                    baru = copy.deepcopy(umum.PROFIL_DEFAULT)
                    baru.update(nama=nick, nick=nick, id_game=id_game, target=aktif.get("target"),
                                label=aktif.get("label", "DMG Per Second"), area=aktif.get("area"))
                    self.cfg["profil"][pid] = baru
                    lanjut = (f"Karakter baru, catatannya dibuat.\n👉 Isi job & data pembeli: "
                              f"<code>/input {id_game}</code>")
                else:
                    self.cfg["profil"][pid]["nick"] = nick
                    data = catatan.baca_ok(pid)
                    lanjut = ("Catatan lama dilanjutkan. DPS terakhir: "
                              f"{umum.fmt(data[-1]['dps'])}" if data else "Catatan lama dilanjutkan.")
                self._aktifkan_profil(pid)
                pesan = (f"🔄 <b>Ganti karakter: {html.escape(nick)}</b> (ID {id_game})\n{lanjut}\n"
                         "Lihat semua karakter: /daftar")
                h = self.hasil_terakhir
                if h and h["pid"] == pid_lama and time.time() - h["jam"] <= 15 * 60:
                    lama_nama = self.nama_akun(self.cfg["profil"].get(pid_lama, {}))
                    pesan += (f"\n\n⚠️ Hasil terakhir DPS <b>{umum.fmt(h['dps'])}</b> ({h['waktu'][11:]}) "
                              f"tadi masuk ke <b>{lama_nama}</b>.\nKalau itu milik "
                              f"<b>{html.escape(nick)}</b>, ketik /pindah")
        self.log.info("Karakter terlihat: %s (ID %s) -> profil %s", nick, id_game, self.pid)
        self.siarkan_teks(pesan)

    def foto_game(self, area: dict | None):
        """Screenshot satu jendela game penuh (karakter + angka). None kalau tidak bisa."""
        judul = str(self.cfg.get("judul_jendela_game") or "").strip()
        if not judul:
            return None
        try:
            jendela = layar.jendela_game(judul)
            if not jendela:
                return None
            h_pilih, pilih = jendela[0]
            if area:
                cx, cy = area["left"] + area["width"] // 2, area["top"] + area["height"] // 2
                for h, a in jendela:
                    if a["left"] <= cx < a["left"] + a["width"] and a["top"] <= cy < a["top"] + a["height"]:
                        h_pilih, pilih = h, a
            return self._ambil_jendela(h_pilih) or layar.ambil_area(pilih)
        except Exception as e:
            self.log.warning("Screenshot jendela game gagal: %s", e)
            return None

    def catat_gagal(self, pid: str, area: dict, alasan: str) -> None:
        # Tidak dicatat ke riwayat. Yang disimpan hanya hasil test DPS yang berhasil.
        self.gagal_berturut += 1
        self.keadaan = f"GAGAL BACA: {alasan}"
        batas = int(self.cfg.get("peringatan_gagal_berturut", 0) or 0)
        if self.gagal_berturut == 1:
            self.log.info("Gagal baca: %s", alasan)
        if batas <= 0:
            return  # peringatan dimatikan
        if self.gagal_berturut >= batas and not self.sudah_warn_gagal:
            self.sudah_warn_gagal = True
            self.peringatan(area, f"⚠️ <b>PERINGATAN</b> - profil <b>{self.nama_aman()}</b>\n"
                                  f"Angka gagal dibaca {self.gagal_berturut}x berturut-turut.\n"
                                  f"Sebab: {html.escape(alasan)}\n"
                                  "Mungkin game crash, ada popup, layar mati, atau disconnect.")

    def cek_tanpa_hasil(self, area: dict) -> None:
        menit = float(self.cfg.get("peringatan_tanpa_hasil_menit", 0) or 0)
        if menit <= 0 or self.sudah_warn_tanpa_hasil:
            return
        if time.time() - self.acuan_tanpa_hasil >= menit * 60:
            self.sudah_warn_tanpa_hasil = True
            self.peringatan(area, f"⚠️ <b>PERINGATAN</b> - profil <b>{self.nama_aman()}</b>\n"
                                  f"Sudah {menit:g} menit tidak ada hasil DPS baru.\n"
                                  "Cek gamenya: mungkin crash, popup, atau disconnect.")

    def peringatan(self, area: dict, teks: str) -> None:
        self.log.warning("Kirim peringatan: %s", teks.replace("\n", " | "))
        teks += f"\n🕒 {datetime.now():%d/%m/%Y %H:%M:%S}"
        try:
            foto = layar.ke_jpg(layar.ambil_layar_penuh(area))
            self.siarkan_foto(teks, [("layar.jpg", foto)])
        except Exception as e:
            self.siarkan_teks(teks + f"\n(Screenshot layar penuh juga gagal: {html.escape(str(e))})")

    def cek_afk(self) -> None:
        """Catat AFK: lebih dari `afk_menit` tidak memakai mouse/keyboard DI JENDELA GAME.
        Browsing, YouTube, chat, dll di aplikasi lain = tetap AFK.
        Hanya membaca jam idle & judul jendela aktif dari Windows, tidak menyentuh game."""
        batas = float(self.cfg.get("afk_menit", 5) or 0)
        diam = harian.detik_diam() if batas > 0 else None
        if diam is None:
            return
        sekarang = datetime.now().replace(microsecond=0)
        judul = str(self.cfg.get("judul_jendela_game") or "").strip()
        sentuhan = sekarang - timedelta(seconds=int(diam))
        try:
            di_game = layar.game_di_depan(judul) if judul else True  # tanpa judul: semua aplikasi dihitung
        except Exception:
            di_game = True
        if di_game:
            self.aktif_di_game = max(self.aktif_di_game, sentuhan)
        terakhir_disentuh = self.aktif_di_game
        diam = (sekarang - terakhir_disentuh).total_seconds()
        if diam >= batas * 60:
            if self.afk_mulai is None:
                self.afk_mulai = terakhir_disentuh
                self.log.info("AFK sejak %s", f"{terakhir_disentuh:%H:%M:%S}")
        elif self.afk_mulai is not None:
            mulai, self.afk_mulai = self.afk_mulai, None
            if terakhir_disentuh > mulai:
                harian.catat_afk(mulai, terakhir_disentuh)
                self.log.info("AFK selesai: %s - %s", f"{mulai:%H:%M:%S}", f"{terakhir_disentuh:%H:%M:%S}")

    def loop_pantau(self) -> None:
        while not self.berhenti.is_set():
            try:
                self.cek_afk()
            except Exception:
                self.log.exception("Error saat cek AFK (bot tetap jalan)")
            if not self.jeda:
                try:
                    self.cek_sekali()
                except Exception:
                    self.log.exception("Error saat cek (bot tetap jalan)")
            interval = max(1, int(self.cfg.get("interval_detik", 2)))
            self.bangun.wait(interval)
            self.bangun.clear()

    # ------------------------------------------------------------ perintah Telegram

    def loop_perintah(self) -> None:
        offset = None
        sudah_log_putus = False
        while not self.berhenti.is_set():
            try:
                if offset is None:
                    # Pesan yang dikirim saat bot mati dibuang, supaya /stop lama tidak tiba-tiba jalan.
                    lama = self.tg.panggil("getUpdates", {"offset": -1, "timeout": 0}, timeout=20)
                    offset = lama[-1]["update_id"] + 1 if lama else 0
                daftar = self.tg.ambil_update(offset)
                if sudah_log_putus:
                    self.log.info("Koneksi ke Telegram tersambung lagi.")
                    sudah_log_putus = False
            except TelegramSementara as e:
                if not sudah_log_putus:
                    self.log.warning("Koneksi ke Telegram putus (%s). Dicoba terus...", e)
                    sudah_log_putus = True
                time.sleep(5)
                continue
            except TelegramError as e:
                if str(e).startswith("409"):
                    self.log.error("Bot ini sedang dijalankan di tempat lain juga (dobel). Tutup salah satunya.")
                else:
                    self.log.error("Telegram menolak: %s", e)
                time.sleep(15)
                continue
            for u in daftar:
                offset = u["update_id"] + 1
                try:
                    self.tangani(u.get("message") or {})
                except Exception:
                    self.log.exception("Error saat memproses perintah (bot tetap jalan)")

    def tangani(self, pesan: dict) -> None:
        chat_id = (pesan.get("chat") or {}).get("id")
        # File yang dikirim dengan caption (/update) teksnya ada di "caption", bukan "text".
        teks = (pesan.get("text") or pesan.get("caption") or "").strip()
        if pesan.get("document") and chat_id in self.dev_ids:
            # Simpan file dari developer: dipakai /update (album beberapa file, atau file dulu lalu /update).
            with self.kunci:
                antre = [x for x in self.dok_tunggu.get(chat_id, []) if time.time() - x[0] <= 600]
                antre.append((time.time(), pesan.get("media_group_id"), pesan["document"]))
                self.dok_tunggu[chat_id] = antre[-30:]
        if chat_id is None or not teks:
            return
        if chat_id not in self.chat_ids and chat_id not in self.dev_ids:
            # KEAMANAN: orang lain diabaikan total, tidak dibalas.
            self.log.warning("Pesan dari chat_id tak dikenal %s diabaikan.", chat_id)
            return
        if not teks.startswith("/"):
            if chat_id in self.isian:
                self.lanjut_isian(chat_id, teks)
            else:
                # Misalnya bot sempat restart di tengah /input: jangan diam saja.
                self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id,
                                  "ℹ️ Tidak ada /input yang sedang berjalan (mungkin bot sempat restart).\n"
                                  "Mulai lagi: /input  |  Daftar perintah: /help", None, True)
            return
        if chat_id in self.isian and teks.split()[0].lower() != "/input":
            self.isian.pop(chat_id, None)
            self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id, "❌ Input data dibatalkan.", None, True)
            if teks.lower().startswith("/batal"):
                return
        self.muat_ulang_jika_berubah()
        kata = teks.split(maxsplit=1)
        perintah = kata[0].lower().split("@")[0]
        isi = kata[1].strip() if len(kata) > 1 else ""
        # " [dev]" = dari developer, supaya /pemakaian hanya menghitung perintah Philip
        self.log.info("Perintah: %s %s%s", perintah, isi,
                      " [dev]" if chat_id in self.dev_ids and chat_id not in self.chat_ids else "")
        m = re.fullmatch(r"(/[a-z_]+?)(\d+)", perintah)  # salah ketik spasi: "/lihat24" = "/lihat 24"
        if m:
            perintah, isi = m.group(1), f"{m.group(2)} {isi}".strip()
        if perintah in ("/update", "/auto_update", "/tarik_update", "/siar_tutor", "/dev_mode", "/devmode", "/log", "/restart", "/dev", "/data_latih", "/pemakaian"):
            if chat_id not in self.dev_ids:
                self.balas(chat_id, "Perintah ini khusus developer.")
                return
            {"/update": lambda c, i: self.p_update(c, i, pesan),
             "/auto_update": self.p_auto_update,
             "/tarik_update": lambda c, i: self.p_auto_update(c, "cek"),
             "/siar_tutor": self.p_siar_tutor,
             "/dev_mode": self.p_dev_mode,
             "/devmode": self.p_dev_mode, "/log": self.p_log, "/restart": self.p_restart,
             "/data_latih": self.p_data_latih,
             "/pemakaian": lambda c, i: self.balas(c, pemakaian.laporan(
                 umum.FOLDER_LOG, int(i) if i.strip().isdigit() else 7)),
             "/dev": lambda c, i: self.balas(c, BANTUAN_DEV)}[perintah](chat_id, isi)
            return
        fungsi = {
            "/help": self.p_help, "/ss": self.p_ss, "/status": self.p_status,
            "/target": self.p_target, "/job": self.p_job, "/stop": self.p_stop, "/start": self.p_start,
            "/matikan": self.p_matikan, "/shutdown": self.p_matikan,
            "/daftar": self.p_daftar, "/list": self.p_daftar,"/lihat": self.p_lihat, "/pilih": self.p_pilih, "/rapor": self.p_rapor,
            "/grafik": self.p_grafik, "/chart": self.p_grafik,
            "/gif": self.p_gif, "/animasi": self.p_gif,
            "/story": self.p_story, "/poster": self.p_story,
            "/papan": self.p_papan, "/board": self.p_papan, "/antrean": self.p_papan,
            "/rekor": self.p_rekor, "/hof": self.p_rekor, "/prestasi": self.p_rekor,
            "/input": self.p_input, "/arsip": self.p_arsip, "/batal": lambda c, i: None,
            "/pindah": self.p_pindah, "/hari": self.p_hari, "/ringkasan": self.p_hari, "/db": self.p_db,
            "/tagihan": self.p_tagihan, "/stat": self.p_stat,
            "/sasaran": self.p_sasaran,
            "/saran": self.p_saran, "/advice": self.p_saran,
            "/sim": self.p_sim, "/simulasi": self.p_sim, "/calc": self.p_sim,
            "/batu": self.p_batu, "/saran_batu": self.p_batu, "/gem_saran": self.p_batu,
            "/record_train": self.p_rekam, "/rekam": self.p_rekam, "/train": self.p_rekam,
            "/stop_train": self.p_rekam_stop, "/rekam_stop": self.p_rekam_stop,
        }.get(perintah)
        if fungsi is None:
            self.balas(chat_id, "Perintah tidak dikenal. Ketik /help")
            return
        fungsi(chat_id, isi)

    def p_help(self, chat_id, isi):
        self.balas(chat_id, BANTUAN + ("\n\n" + BANTUAN_DEV if chat_id in self.dev_ids else ""))

    def p_ss(self, chat_id, isi):
        try:
            area = self.profil.get("area")
            foto = layar.ke_jpg(layar.ambil_layar_penuh(area if umum.area_valid(area) else self.area_terdeteksi))
        except Exception as e:
            self.balas(chat_id, f"Screenshot gagal: {html.escape(str(e))}")
            return
        self.siarkan_foto(f"🖥 Layar penuh - {datetime.now():%d/%m/%Y %H:%M:%S}", [("layar.jpg", foto)], [chat_id])

    def p_status(self, chat_id, isi):
        with self.kunci:
            pid, profil = self.pid, self.profil
            target = int(profil.get("target") or 0)
            data = catatan.baca_ok(pid, catatan.sesi_mulai(pid))
            baris = [f"📋 <b>STATUS</b> {'⏸ DIJEDA' if self.jeda else '▶️ aktif'}",
                     f"👤 Profil: <b>{self.nama_aman()}</b>",
                     f"👤 Akun: <b>{self.nama_akun(profil)}</b>"
                     + ("" if profil.get("nick") else " (nick belum terbaca: buka halaman info karakter di game)")
                     + self.teks_karakter(profil)]
            if data:
                d = max(data, key=lambda x: x["dps"])
                tanda = "✅ tercapai" if d["dps"] >= target else f"kurang {umum.fmt(target - d['dps'])}"
                baris.append(f"⚔️ DPS terbaik: <b>{umum.fmt(d['dps'])}</b> ({d['waktu']:%d/%m %H:%M:%S})")
                baris.append(f"🎯 Target: {umum.fmt(target)} ({tanda})")
            else:
                baris.append("⚔️ DPS terbaik: belum ada di sesi ini")
                baris.append(f"🎯 Target: {umum.fmt(target)}")
            cek = f"{self.cek_terakhir:%H:%M:%S}" if self.cek_terakhir else "-"
            baris += [f"🕒 Cek terakhir: {cek} ({html.escape(self.keadaan)})",
                      f"⚙️ Cek tiap {self.cfg['interval_detik']} detik"]
        self.balas(chat_id, "\n".join(baris))

    def p_target(self, chat_id, isi):
        nilai = ocr.parse_angka(isi)
        if not nilai or nilai <= 0:
            self.balas(chat_id, "Contoh: <code>/target 3000000</code> atau <code>/target 3.5M</code>")
            return
        with self.kunci:
            self.profil["target"] = nilai
            self.simpan()
            data = catatan.baca_ok(self.pid, catatan.sesi_mulai(self.pid))
            sudah = bool(data) and data[-1]["dps"] >= nilai
            self.target_tercapai[self.pid] = sudah
        catatan_tambahan = "\nDPS terakhir sudah di atas target ini." if sudah else ""
        self.balas(chat_id, f"🎯 Target <b>{self.nama_aman()}</b> = {umum.fmt(nilai)}{catatan_tambahan}")

    def _daftar_karakter(self) -> list[tuple[str, dict, dict | None, int]]:
        """[(pid, profil, hasil terakhir yang disimpan, jumlah hasil)] urut sesuai urutan dibuat."""
        hasil = []
        for pid, p in self.cfg["profil"].items():
            data = catatan.baca_ok(pid)
            hasil.append((pid, p, data[-1] if data else None, len(data)))
        return hasil

    def p_daftar(self, chat_id, isi):
        with self.kunci:
            daftar = self._daftar_karakter()
        baris = [f"📒 <b>DAFTAR KARAKTER</b> ({len(daftar)})"]
        for i, (pid, p, akhir, jumlah) in enumerate(daftar, 1):
            tanda = f"{i}. ▶️" if pid == self.pid else f"{i}."
            nama = html.escape(str(p.get("nick") or p.get("nama")))
            job_ = html.escape(str(p.get("job") or "job ?"))
            baris.append(f"\n{tanda} <b>{nama}</b> - {job_}" + (f" (ID {p['id_game']})" if p.get("id_game") else ""))
            if akhir:
                baris.append(f"   ⚔️ DPS terakhir: <b>{umum.fmt(akhir['dps'])}</b> ({akhir['waktu']:%d/%m %H:%M})"
                             f" | {jumlah} hasil")
            else:
                baris.append("   ⚔️ belum ada hasil")
            info = " | ".join(html.escape(str(x)) for x in (p.get("kontak"), p.get("paket"), p.get("bayar")) if x)
            if info:
                baris.append(f"   📱 {info}")
        baris.append("\nFoto & detail: <code>/lihat 1</code> (nomor) atau <code>/lihat Soloish97</code>")
        self.balas(chat_id, "\n".join(baris))

    def _pilih_karakter(self, chat_id, isi):
        """'2' (nomor di /daftar), nick, nama, atau ID game. Kosong = karakter aktif."""
        with self.kunci:
            daftar = self._daftar_karakter()
        isi = isi.strip().lower()
        pilih = None
        if isi.isdigit() and 1 <= int(isi) <= len(daftar):
            pilih = daftar[int(isi) - 1]
        elif isi:
            pilih = next((d for d in daftar if isi in (str(d[1].get("nick") or "").lower(),
                                                       str(d[1].get("nama")).lower(),
                                                       str(d[1].get("id_game") or ""))), None)
            if not pilih:  # salah ketik / sebagian nama: cari yang paling mirip
                import difflib

                def bersih(t):
                    return re.sub(r"[^a-z0-9]", "", str(t or "").lower())
                k = bersih(isi)
                skor = []
                for d in daftar:
                    for n in {bersih(d[1].get("nick")), bersih(d[1].get("nama"))} - {""}:
                        r = difflib.SequenceMatcher(None, k, n).ratio()
                        if k and (n.startswith(k) or k in n):
                            r = max(r, 0.85)
                        skor.append((r, d))
                if skor:
                    r, d = max(skor, key=lambda x: x[0])
                    pilih = d if r >= 0.6 else None
        elif daftar:
            pilih = next((d for d in daftar if d[0] == self.pid), daftar[0])
        if not pilih:
            self.balas(chat_id, "Karakter tidak ditemukan. Ketik /daftar untuk melihat nomornya.")
        return pilih

    def p_pilih(self, chat_id, isi):
        if not isi.strip():
            self.balas(chat_id, "Contoh: <code>/pilih 2</code> (nomor dari /daftar) atau <code>/pilih Soloish97</code>")
            return
        pilih = self._pilih_karakter(chat_id, isi)
        if not pilih:
            return
        with self.kunci:
            self._aktifkan_profil(pilih[0])
            p = self.profil
        self.balas(chat_id, f"▶️ Karakter aktif: <b>{self.nama_akun(p)}</b>{self.teks_karakter(p)}\n"
                            f"🎯 Target: {umum.fmt(p.get('target'))}\nHasil test berikutnya masuk ke karakter ini.")

    def p_pindah(self, chat_id, isi):
        """Pindahkan hasil DPS terakhir ke karakter aktif (salah masuk karena info karakter
        baru dibuka SETELAH test)."""
        h = self.hasil_terakhir
        if not h:
            self.balas(chat_id, "Tidak ada hasil DPS baru yang bisa dipindah (atau bot sempat restart).")
            return
        with self.kunci:
            tujuan = self.pid
            if h["pid"] == tujuan:
                self.balas(chat_id, f"Hasil terakhir ({umum.fmt(h['dps'])}) sudah ada di "
                                    f"<b>{self.nama_akun(self.profil)}</b>.")
                return
            asal_nama = self.nama_akun(self.cfg["profil"].get(h["pid"], {}))
            baris = catatan.pindah_hasil(h["pid"], tujuan, h["waktu"])
            if not baris:
                self.balas(chat_id, "Hasil itu tidak ditemukan lagi di catatan (mungkin sudah dipindah).")
                return
            h["pid"] = tujuan
            self.target_tercapai.pop(tujuan, None)
            tujuan_nama = self.nama_akun(self.profil)
        self.log.info("Hasil %s (%s) dipindah: %s -> %s", h["dps"], h["waktu"], asal_nama, tujuan_nama)
        self.balas(chat_id, f"✅ DPS <b>{umum.fmt(h['dps'])}</b> ({h['waktu'][11:]}) dipindah dari "
                            f"<b>{asal_nama}</b> ke <b>{tujuan_nama}</b>.")

    def p_rapor(self, chat_id, isi):
        pilih = self._pilih_karakter(chat_id, isi)
        if not pilih:
            return
        pid, p = pilih[0], pilih[1]
        if not self.kirim_rapor(pid, p, "Rapor - tinggal teruskan gambar ini ke pembeli", [chat_id]):
            self.balas(chat_id, f"<b>{self.nama_akun(p)}</b> belum punya hasil DPS tersimpan (atau rapor gagal dibuat, cek log).")

    def p_grafik(self, chat_id, isi):
        """/grafik [nama/nomor] - gambar grafik tren DPS 1 karakter."""
        pilih = self._pilih_karakter(chat_id, isi)
        if not pilih:
            return
        pid, p = pilih[0], pilih[1]
        try:
            jpg = rapor.buat_grafik(pid, p)
        except Exception as e:
            self.log.exception("Gagal membuat grafik")
            self.balas(chat_id, f"Gagal membuat grafik: {html.escape(str(e))}")
            return
        if not jpg:
            self.balas(chat_id, f"<b>{self.nama_akun(p)}</b> butuh minimal 2 hasil test untuk membuat grafik.")
            return
        self.kirim.tambah("grafik", self.tg.kirim_foto, chat_id, jpg,
                          f"📈 Grafik progres DPS <b>{self.nama_akun(p)}</b>", "grafik.jpg")

    def p_rekor(self, chat_id, _isi):
        """/rekor - poster Hall of Fame & motivasi Philip (total klien, tembus target, top 5, streak)."""
        try:
            daftar = [(pid, p) for pid, p, _, _ in self._daftar_semua()]
            hasil = rapor.buat_hof(daftar, str(self.cfg.get("rapor_catatan_kaki") or ""))
        except Exception as e:
            self.log.exception("Gagal membuat Hall of Fame")
            self.balas(chat_id, f"Gagal membuat Hall of Fame: {html.escape(str(e))}")
            return
        if not hasil:
            self.balas(chat_id, "Belum ada data test tersimpan.")
            return
        jpg, info = hasil
        cap = (f"🏆 <b>Hall of Fame — {html.escape(info['pangkat'])}</b>\n"
               f"👥 {info['klien']} klien · 🎯 {info['tembus']} tembus target · "
               f"🔥 Streak {info['streak']} hari ({info['test']} test)")
        self.kirim.tambah("rekor", self.tg.kirim_foto, chat_id, jpg, cap, "hall_of_fame.jpg")

    def p_gif(self, chat_id, isi):
        """/gif [nama/nomor] - animasi GIF Before -> After siap forward klien / WA Story."""
        pilih = self._pilih_karakter(chat_id, isi)
        if not pilih:
            return
        pid, p = pilih[0], pilih[1]
        self.balas(chat_id, f"🎬 Merender animasi <b>{self.nama_akun(p)}</b>...")
        try:
            hasil = visual.buat_gif(pid, p, str(self.cfg.get("rapor_catatan_kaki") or ""))
        except Exception as e:
            self.log.exception("Gagal membuat GIF")
            self.balas(chat_id, f"Gagal membuat animasi: {html.escape(str(e))}")
            return
        if not hasil:
            self.balas(chat_id, f"<b>{self.nama_akun(p)}</b> belum punya hasil DPS tersimpan.")
            return
        gif_bytes, r = hasil
        cap = (f"🎬 <b>{self.nama_akun(p)}</b>: {umum.fmt(r['awal'])} → <b>{umum.fmt(r['terbaik'])}</b> "
               f"({r['naik']:+.1f}%)".replace(".", ","))
        self.kirim.tambah("gif", self.tg.kirim_animasi, chat_id, gif_bytes, cap, "progres_dps.gif")

    def p_story(self, chat_id, isi):
        """/story [nama/nomor] - poster vertikal 9:16 siap upload WA Status / TikTok / IG Story."""
        pilih = self._pilih_karakter(chat_id, isi)
        if not pilih:
            return
        pid, p = pilih[0], pilih[1]
        try:
            hasil = visual.buat_story(pid, p, str(self.cfg.get("rapor_catatan_kaki") or ""))
        except Exception as e:
            self.log.exception("Gagal membuat Story")
            self.balas(chat_id, f"Gagal membuat Story: {html.escape(str(e))}")
            return
        if not hasil:
            self.balas(chat_id, f"<b>{self.nama_akun(p)}</b> belum punya hasil DPS tersimpan.")
            return
        jpg, r = hasil
        cap = (f"📱 Poster 9:16 <b>{self.nama_akun(p)}</b> ({r['naik']:+.1f}%) — siap upload WA Status / TikTok!"
               .replace(".", ","))
        self.kirim.tambah("story", self.tg.kirim_foto, chat_id, jpg, cap, "story_dps.jpg")

    def p_papan(self, chat_id, _isi):
        """/papan - dashboard Kanban visual antrean orderan (Prioritas Kerja | Siap Ditagih | Lunas)."""
        try:
            daftar = [(pid, p) for pid, p, _, _ in self._daftar_semua()]
            hasil = visual.buat_papan(daftar, str(self.cfg.get("rapor_catatan_kaki") or ""))
        except Exception as e:
            self.log.exception("Gagal membuat papan")
            self.balas(chat_id, f"Gagal membuat papan: {html.escape(str(e))}")
            return
        if not hasil:
            self.balas(chat_id, "Belum ada data klien tersimpan.")
            return
        jpg, info = hasil
        cap = (f"📋 <b>Papan Antrean Orderan</b>\n"
               f"🟠 {info['proses']} Prioritas Kerja · 🟢 {info['siap']} Siap Ditagih · 🔵 {info['lunas']} Lunas")
        self.kirim.tambah("papan", self.tg.kirim_foto, chat_id, jpg, cap, "papan_orderan.jpg")

    def p_siar_tutor(self, chat_id, _isi):
        """(Dev) Kirim tutorial singkat fitur baru + contoh nyata (/papan & /gif) ke Philip + dev."""
        daftar = [(pid, p) for pid, p, _, _ in self._daftar_semua()]
        kaki = str(self.cfg.get("rapor_catatan_kaki") or "")
        teks = (
            "🚀 <b>Update Fitur Baru Bot DPS Philip!</b>\n\n"
            "Biar kerja makin cepat & konten promosi makin keren, ini perintah baru yang bisa langsung dicoba:\n\n"
            "1️⃣ <b>/papan</b> — Papan antrean orderan visual (langsung kelihatan mana akun yang paling dekat target & mana yang siap ditagih)\n"
            "2️⃣ <b>/gif</b> (atau <code>/gif 2</code>) — Animasi Before → After otomatis, tinggal forward ke klien / WA Story\n"
            "3️⃣ <b>/story</b> (atau <code>/story 2</code>) — Poster vertikal 9:16 siap upload WA Status / TikTok\n"
            "4️⃣ <b>/rapor</b> — Desain rapor baru + grafik kurva progres & Rank Badge\n"
            "5️⃣ <b>/rekor</b> — Poster Hall of Fame & Streak kamu\n"
            "6️⃣ <b>/sim +10% pdmg</b> — Simulasi kenaikan DPS sebelum ganti build (bisa gabung: <code>/sim +300 matk +15% vs medium</code>)\n"
            "7️⃣ <b>/saran</b> &amp; <b>/db</b> — Sekarang ada prioritas stat, Affix/Stunt, Pet, Rune, Apocalypse, dan Refine!\n\n"
            "👇 Di bawah ini contoh langsung dari datamu:"
        )
        self.siarkan_teks(teks)
        # Kirim contoh /papan
        try:
            papan = visual.buat_papan(daftar, kaki)
            if papan:
                jpg, _ = papan
                for cid in self.penerima:
                    self.kirim.tambah("tutor-papan", self.tg.kirim_foto, cid, jpg,
                                      "📋 Contoh <b>/papan</b> — cek antrean & prioritas kerja tiap hari", "papan.jpg")
        except Exception:
            self.log.exception("Gagal kirim contoh papan")
        # Cari 1 klien dengan kenaikan bagus + punya foto untuk contoh /gif
        calon = None
        for pid, p in daftar:
            if pid == "akun1":
                continue
            ok = catatan.baca_ok(pid)
            if len(ok) >= 3 and ok[-1]["dps"] > ok[0]["dps"]:
                calon = (pid, p)
                break
        if calon:
            try:
                g = visual.buat_gif(calon[0], calon[1], kaki)
                if g:
                    gif_bytes, _ = g
                    for cid in self.penerima:
                        self.kirim.tambah("tutor-gif", self.tg.kirim_animasi, cid, gif_bytes,
                                          f"🎬 Contoh <b>/gif</b> ({self.nama_akun(calon[1])}) — tinggal forward ke klien!",
                                          "contoh_progres.gif")
            except Exception:
                self.log.exception("Gagal kirim contoh gif")

    def p_lihat(self, chat_id, isi):
        pilih = self._pilih_karakter(chat_id, isi)
        if not pilih:
            return
        pid, p, akhir, jumlah = pilih
        nama = html.escape(str(p.get("nick") or p.get("nama")))
        baris = [f"👤 Akun: <b>{nama}</b>" + (f" (ID {p['id_game']})" if p.get("id_game") else ""),
                 f"🧙 Job: <b>{html.escape(str(p.get('job') or '-'))}</b>"]
        for ikon, k in (("📱 Kontak", "kontak"), ("💰 Paket", "paket"), ("💳 Bayar", "bayar"),
                        ("📅 Order", "tanggal_order"), ("📝 Catatan", "catatan")):
            if p.get(k):
                baris.append(f"{ikon}: {html.escape(str(p[k]))}")
        if not akhir:
            self.balas(chat_id, "\n".join(baris + ["⚔️ Belum ada hasil DPS tersimpan."]))
            return
        semua = catatan.baca_ok(pid)
        awal = semua[0]
        baris += [f"⚔️ DPS terakhir: <b>{umum.fmt(akhir['dps'])}</b>",
                  f"📈 Dari {umum.fmt(awal['dps'])} ({awal['waktu']:%d/%m}) → {umum.fmt(akhir['dps'])}"
                  f"{persen(akhir['dps'], awal['dps'])}"]
        if akhir.get("total"):
            baris.append(f"💥 Total DMG: {umum.fmt(akhir['total'])}")
        baris += [f"🔁 {jumlah} hasil tersimpan", f"🕒 {akhir['waktu']:%d/%m/%Y %H:%M:%S}"]
        f = catatan.folder_profil(pid) / "gambar" / akhir["gambar"] if akhir.get("gambar") else None
        if f and f.exists():
            self.siarkan_foto("\n".join(baris), [(f"hasil{f.suffix}", f.read_bytes())], [chat_id])
        else:
            self.balas(chat_id, "\n".join(baris + ["(foto tidak ada)"]))

    # ------------------------------------------------------------ /input data pembeli jasa

    LANGKAH = [
        ("id_game", "🆔 Ketik <b>ID</b> pemain (angka di halaman info karakter, contoh 60542798):"),
        ("nick", "👤 Ketik <b>nick</b> karakternya:"),
        ("job", "🧙 Pilih <b>job</b>:"),
        ("kontak", "📱 <b>Kontak pembeli</b> (WA / TikTok / IG / nama):"),
        ("paket", "💰 <b>Paket / harga</b> (pilih atau ketik, contoh 150k):"),
        ("target", "🎯 <b>Target DPS</b> (pilih atau ketik, contoh 3jt / 5.5M):"),
        ("bayar", "💳 <b>Status bayar</b>:"),
        ("catatan", "📝 <b>Catatan</b> (request build, deadline, dll):"),
    ]
    LEWATI = "Lewati"

    def _tombol_langkah(self, kunci_: str, lama: str) -> list[list[str]]:
        lewati = [self.LEWATI + (" (tetap)" if lama else "")]
        if kunci_ == "job":
            j = job.daftar_job()
            return [j[i:i + 3] for i in range(0, len(j), 3)] + ([lewati] if lama else [])
        if kunci_ == "paket":
            return [["50k", "100k", "150k"], ["200k", "300k"], lewati]
        if kunci_ == "target":
            return [["3jt", "5jt", "8jt"], ["10jt", "15jt"], lewati]
        if kunci_ == "bayar":
            return [["Lunas", "DP", "Belum bayar"]] + ([lewati] if lama else [])
        if kunci_ == "id_game":
            return []
        return [lewati]

    def _tanya(self, chat_id: int) -> None:
        st = self.isian[chat_id]
        i = st["langkah"]
        if i >= len(self.LANGKAH):
            d = st["data"]
            baris = ["📋 <b>Cek dulu datanya:</b>",
                     f"🆔 ID: <b>{html.escape(d['id_game'])}</b>",
                     f"👤 Nick: {html.escape(d.get('nick') or '-')}",
                     f"🧙 Job: {html.escape(d.get('job') or '-')}",
                     f"📱 Kontak: {html.escape(d.get('kontak') or '-')}",
                     f"💰 Paket: {html.escape(d.get('paket') or '-')}",
                     f"🎯 Target: {umum.fmt(d['target']) if d.get('target') else '-'}",
                     f"💳 Bayar: {html.escape(d.get('bayar') or '-')}",
                     f"📝 Catatan: {html.escape(d.get('catatan') or '-')}"]
            self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id, "\n".join(baris), [["✅ Simpan", "❌ Batal"]])
            return
        kunci_, tanya = self.LANGKAH[i]
        lama = st["data"].get(kunci_)
        if kunci_ == "target" and lama:
            lama = umum.fmt(lama)
        teks = f"<b>{i + 1}/{len(self.LANGKAH)}</b> {tanya}"
        if lama and kunci_ != "id_game":
            teks += f"\n(sekarang: <b>{html.escape(str(lama))}</b>)"
        teks += "\nKetik /batal untuk berhenti."
        self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id, teks,
                          self._tombol_langkah(kunci_, str(lama or "")) or None, True)

    def p_input(self, chat_id, isi):
        self.isian[chat_id] = {"langkah": 0, "data": {}, "waktu": time.time()}
        self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id,
                          "🗂 <b>INPUT DATA PEMBELI JASA</b>\nJawab pertanyaannya satu per satu. "
                          "Kalau ID sudah pernah diinput, datanya akan diperbarui.", None, True)
        if isi.strip().isdigit():  # /input 60542798 -> langsung isi ID
            self.lanjut_isian(chat_id, isi.strip())
        else:
            self._tanya(chat_id)

    def lanjut_isian(self, chat_id: int, teks: str) -> None:
        st = self.isian[chat_id]
        if time.time() - st["waktu"] > 30 * 60:
            self.isian.pop(chat_id, None)
            self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id,
                              "⌛ Input data kedaluwarsa (lebih dari 30 menit). Mulai lagi dengan /input", None, True)
            return
        st["waktu"] = time.time()
        d, i = st["data"], st["langkah"]
        teks = teks.strip()

        if i >= len(self.LANGKAH):  # konfirmasi
            if "simpan" in teks.lower():
                self.isian.pop(chat_id, None)
                self.simpan_pembeli(chat_id, d)
            elif "batal" in teks.lower():
                self.isian.pop(chat_id, None)
                self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id, "❌ Tidak disimpan.", None, True)
            else:
                self._tanya(chat_id)
            return

        kunci_ = self.LANGKAH[i][0]
        lewati = teks.lower().startswith(self.LEWATI.lower()) or teks == "-"

        def ulang(pesan: str) -> None:
            self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id, f"⚠️ {pesan}",
                              self._tombol_langkah(kunci_, str(d.get(kunci_) or "")) or None, True)

        if kunci_ == "id_game":
            nomor = re.sub(r"\D", "", teks)
            if not 4 <= len(nomor) <= 12:
                ulang("ID harus angka (4-12 digit). Ketik lagi:")
                return
            d["id_game"] = nomor
            with self.kunci:
                ada = next((p for p in self.cfg["profil"].values() if p.get("id_game") == nomor), None)
            if ada:  # pemain lama: isi dengan data yang sudah ada, tinggal Lewati yang tidak berubah
                for k in ("nick", "job", "kontak", "paket", "bayar", "catatan", "target"):
                    if ada.get(k):
                        d[k] = ada[k]
                self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id,
                                  f"ℹ️ ID ini sudah ada (<b>{html.escape(str(ada.get('nick') or ada.get('nama')))}</b>). "
                                  "Pilih <b>Lewati (tetap)</b> untuk data yang tidak berubah.", None, False)
        elif lewati:
            pass  # biarkan nilai lama / kosong
        elif kunci_ == "job":
            nama = job.nama_resmi(teks)
            if not nama:
                ulang("Pilih job dari tombol:")
                return
            d["job"] = nama
        elif kunci_ == "target":
            nilai = ocr.parse_angka(teks)
            if not nilai or nilai <= 0:
                ulang("Contoh target: 3jt, 5.5M, 8000000. Ketik lagi:")
                return
            d["target"] = nilai
        elif kunci_ == "bayar":
            pilihan = {"lunas": "Lunas", "dp": "DP", "belum bayar": "Belum bayar", "belum": "Belum bayar"}
            if teks.lower() not in pilihan:
                ulang("Pilih dari tombol: Lunas / DP / Belum bayar")
                return
            d["bayar"] = pilihan[teks.lower()]
        else:
            d[kunci_] = teks[:80]
        st["langkah"] += 1
        self._tanya(chat_id)

    def simpan_pembeli(self, chat_id: int, d: dict) -> None:
        with self.kunci:
            aktif = self.profil
            pid = next((k for k, p in self.cfg["profil"].items() if p.get("id_game") == d["id_game"]), None)
            baru = pid is None
            if baru:
                pid = umum.id_profil(d.get("nick") or f"id_{d['id_game']}")
                if pid in self.cfg["profil"]:
                    pid = f"{pid}_{d['id_game'][-4:]}"
                p = copy.deepcopy(umum.PROFIL_DEFAULT)
                p.update(label=aktif.get("label", "DMG Per Second"), area=aktif.get("area"),
                         target=aktif.get("target"), tanggal_order=datetime.now().strftime("%Y-%m-%d"))
                self.cfg["profil"][pid] = p
            p = self.cfg["profil"][pid]
            for k in ("id_game", "nick", "job", "kontak", "paket", "bayar", "catatan", "target"):
                if d.get(k):
                    p[k] = d[k]
            p["nama"] = p.get("nick") or f"ID {p['id_game']}"
            if not p.get("tanggal_order"):
                p["tanggal_order"] = datetime.now().strftime("%Y-%m-%d")
            self._aktifkan_profil(pid)
            nama = html.escape(str(p["nama"]))
        self.log.info("Data pembeli disimpan: %s (ID %s)", p["nama"], p["id_game"])
        self.kirim.tambah("balasan", self.tg.kirim_teks, chat_id,
                          f"✅ Data <b>{nama}</b> {'disimpan' if baru else 'diperbarui'} dan sekarang jadi karakter aktif.\n"
                          "Hasil test DPS berikutnya masuk ke catatan ini.\n"
                          "Semua data: /daftar  |  File Excel: /arsip", None, True)

    def p_arsip(self, chat_id, isi):
        import arsip
        with self.kunci:
            daftar = [(pid, p, catatan.baca_ok(pid)) for pid, p in self.cfg["profil"].items()]
            kaki = self.cfg.get("rapor_catatan_kaki", "")
        try:
            isi_file = arsip.buat(daftar, kaki)
        except Exception as e:  # noqa: BLE001
            self.log.exception("Gagal membuat Excel arsip")
            self.balas(chat_id, f"❌ Gagal membuat file Excel: {html.escape(str(e))}")
            return
        nama = f"arsip_pemain_{datetime.now():%Y%m%d_%H%M}.xlsx"
        try:
            (umum.FOLDER_DATA / "arsip_pemain.xlsx").write_bytes(isi_file)
        except OSError as e:
            self.log.warning("Gagal simpan arsip lokal (mungkin file sedang dibuka di Excel): %s", e)
        self.kirim.tambah("arsip", self.tg.kirim_dokumen, chat_id, isi_file, nama,
                          f"🗂 Arsip {len(daftar)} pemain (Ringkasan + Riwayat Test). Buka dengan Excel.")

    def p_hari(self, chat_id, isi):
        """Ringkasan satu hari: total waktu kerja (test DPS) + per karakter."""
        tanggal = harian.baca_tanggal(isi)
        if tanggal is None:
            self.balas(chat_id, "Contoh: <code>/hari</code> (hari ini), <code>/hari kemarin</code>, "
                                "<code>/hari 20/11</code>")
            return
        self.balas(chat_id, self.teks_hari(tanggal)[0])

    def teks_hari(self, tanggal) -> tuple[str, int]:
        """(teks ringkasan /hari, jumlah test di tanggal itu)."""
        with self.kunci:
            daftar = [(pid, p, catatan.baca_ok(pid)) for pid, p in self.cfg["profil"].items()]
            jeda = float(self.cfg.get("jeda_istirahat_menit") or 30)
            afk_menit = float(self.cfg.get("afk_menit", 5) or 0)
        afk = harian.baca_afk() if afk_menit > 0 else []
        if self.afk_mulai is not None and afk_menit > 0:  # AFK yang masih berlangsung
            afk.append((self.afk_mulai, datetime.now()))
        jumlah = sum(1 for _, _, data in daftar for d in data if d["waktu"].date() == tanggal)
        return harian.teks(daftar, tanggal, jeda, afk, afk_menit), jumlah

    def ringkasan_malam(self, tanggal) -> str:
        """Ringkasan otomatis: 1 pesan pendek. Detail lengkap tetap lewat /hari dan /tagihan."""
        with self.kunci:
            daftar = [(pid, p, catatan.baca_ok(pid)) for pid, p in self.cfg["profil"].items()]
            jeda = float(self.cfg.get("jeda_istirahat_menit") or 30)
            afk_menit = float(self.cfg.get("afk_menit", 5) or 0)
        afk = harian.baca_afk() if afk_menit > 0 else []
        baris = harian.ringkas(daftar, tanggal, jeda, afk)
        if not baris:
            return ""
        siap, proses, kosong = self._kelompok_tagihan()
        if siap:
            nama_siap = ", ".join(s[0] for s in siap[:5]) + (f" +{len(siap) - 5}" if len(siap) > 5 else "")
            baris.append(f"💰 Siap ditagih ({len(siap)}): {nama_siap}")
        if proses:
            baris.append(f"⏳ Belum lunas & belum target: {len(proses)}")
        return (f"🌙 <b>Ringkasan {harian.HARI[tanggal.weekday()]} {tanggal:%d/%m}</b>\n" + "\n".join(baris)
                + "\nDetail: /hari · /tagihan")

    def _kelompok_tagihan(self):
        """-> (siap ditagih, masih dikerjakan, data pembeli kosong). Tiap item: (nama, teks baris)."""
        siap, proses, kosong = [], [], []
        batas_baru = datetime.now() - timedelta(days=14)
        with self.kunci:
            profil = list(self.cfg["profil"].items())
        for pid, p in profil:
            data = catatan.baca_ok(pid)
            nama = html.escape(str(p.get("nick") or p.get("nama") or pid))
            pembeli = any(p.get(k) for k in ("kontak", "paket", "bayar"))
            if not pembeli:
                if data and data[-1]["waktu"] >= batas_baru:
                    kosong.append(nama)
                continue
            if str(p.get("bayar") or "").lower() == "lunas":
                continue
            target = int(p.get("target") or 0)
            terbaik = max((d["dps"] for d in data), default=0)
            info = " | ".join(html.escape(str(x)) for x in (p.get("paket"), p.get("bayar") or "status bayar ?",
                                                            p.get("kontak")) if x)
            if target and terbaik >= target:
                siap.append((nama, f"• <b>{nama}</b> - {info}\n   ⚔️ {umum.fmt(terbaik)} ≥ target {umum.fmt(target)}"))
            else:
                kurang = f"kurang {(target - terbaik) / terbaik * 100:.1f}%".replace(".", ",") if terbaik and target else "belum ada test"
                proses.append((nama, f"• <b>{nama}</b> - {info}\n   ⚔️ {umum.fmt(terbaik) if terbaik else '-'} ({kurang})"))
        return siap, proses, kosong

    def teks_tagihan(self) -> str:
        """Pembeli yang belum lunas: yang targetnya sudah tercapai (siap ditagih) ditaruh paling atas."""
        siap, proses, kosong = self._kelompok_tagihan()
        siap, proses = [s[1] for s in siap], [s[1] for s in proses]
        baris = ["💰 <b>TAGIHAN</b> (pembeli belum lunas)"]
        if siap:
            baris += ["", f"✅ <b>Target tercapai, siap ditagih ({len(siap)}):</b>"] + siap
        if proses:
            baris += ["", f"⏳ <b>Masih dikerjakan ({len(proses)}):</b>"] + proses
        if not siap and not proses:
            baris.append("Semua pembeli yang datanya diisi sudah lunas 👍")
        if kosong:
            kosong = list(reversed(kosong))  # yang terbaru dibuat duluan
            nama_ = ", ".join(kosong[:8]) + (f", dan {len(kosong) - 8} lainnya" if len(kosong) > 8 else "")
            baris += ["", f"❔ Data pembeli belum diisi ({len(kosong)} karakter aktif 14 hari terakhir): {nama_}",
                      "Isi kontak/paket/status bayar lewat <code>/input</code> supaya ikut terpantau di sini."]
        return "\n".join(baris)

    def p_tagihan(self, chat_id, isi):
        self.balas(chat_id, self.teks_tagihan())

    def loop_harian(self) -> None:
        """Kirim ringkasan hari ini + tagihan otomatis sekali sehari (jam di config, default 23:30).
        Kalau hari itu tidak ada test sama sekali, tidak kirim apa-apa."""
        f = umum.FOLDER_DATA / "ringkasan_terkirim.txt"
        while not self.berhenti.wait(60):
            try:
                jam = str(self.cfg.get("ringkasan_harian_jam", "23:30") or "").strip()
                sekarang = datetime.now()
                if not re.fullmatch(r"\d{1,2}:\d{2}", jam) or sekarang.strftime("%H:%M") < jam.zfill(5):
                    continue
                hari_ini = sekarang.strftime("%Y-%m-%d")
                try:
                    if f.read_text(encoding="utf-8").strip() == hari_ini:
                        continue
                except OSError:
                    pass
                f.write_text(hari_ini, encoding="utf-8")
                teks = self.ringkasan_malam(sekarang.date())
                if teks:  # hari tanpa test = tidak kirim apa-apa
                    self.siarkan_teks(teks)
                    self.log.info("Ringkasan harian otomatis dikirim.")
            except Exception:
                self.log.exception("Gagal kirim ringkasan harian (dicoba lagi besok)")

    def p_db(self, chat_id, isi):
        """Cari detail equip / kartu / skill di database (roworlddb.com, server SEA)."""
        isi = isi.strip()
        if not isi:
            info = datagame.info_lokal()
            self.balas(chat_id, "Contoh: <code>/db Dracula</code>, <code>/db Acid Terror</code>, "
                                "<code>/db Hurricane Fury</code>, <code>/db frenzy 3</code>, <code>/db dom gem</code>\n"
                                "Salah ketik tidak apa-apa.\n<code>/db update</code> = cek pembaruan database"
                                + (f"\n📦 Database versi {info['versi']} (diunduh {info['diunduh']})"
                                   if info.get("versi") else "\n⚠️ Database belum diunduh."))
            return
        if isi.lower() in ("update", "perbarui"):
            try:
                _, pesan = datagame.perbarui(log=self.log.info)
            except Exception as e:  # noqa: BLE001
                pesan = f"Gagal memperbarui: {e}"
            self.balas(chat_id, "📦 " + html.escape(pesan))
            return
        jenis = None
        kata = isi.split(maxsplit=1)
        alias = {"card": "kartu", "eq": "equip", "set": "enchant", "ench": "enchant", "permata": "gem",
                 "apoc": "apocalypse", "stunt": "affix"}
        if kata[0].lower() in ("equip", "eq", "kartu", "card", "skill", "gem", "permata",
                               "enchant", "ench", "set", "rune", "pet", "apocalypse", "apoc", "affix", "stunt") \
                and len(kata) > 1:
            jenis, isi = alias.get(kata[0].lower(), kata[0].lower()), kata[1]
        try:
            hasil = datagame.cari(isi, jenis, 6)
        except datagame.DatabaseError as e:
            self.balas(chat_id, f"⚠️ {html.escape(str(e))}")
            return
        if not hasil:
            self.balas(chat_id, f"Tidak ketemu: <b>{html.escape(isi)}</b>. Coba ketik sebagian namanya saja.")
            return
        ikon = {"equip": "🛡", "kartu": "🃏", "skill": "✨", "gem": "💎", "enchant": "🔮",
                "rune": "💠", "pet": "🐾", "apocalypse": "☄️", "affix": "⚙️"}
        utama = datagame.teks_hasil(hasil[0])
        baris = []
        if hasil[0]["skor"] < 0.9:  # ketikan tidak persis -> beri tahu tebakan kita
            baris.append(f"🔎 Mungkin maksud Anda: <b>{html.escape(hasil[0]['nama'])}</b>")
        baris += [f"{ikon[hasil[0]['jenis']]} <b>{html.escape(utama[0])}</b>"] + [html.escape(b) for b in utama[1:]]
        lain = [h for h in hasil[1:] if h["skor"] >= max(0.7, hasil[0]["skor"] - 0.15)]
        if lain:
            baris.append("\n<b>Mirip:</b>")
            for h in lain:
                ket = ""
                if h["jenis"] == "equip":
                    d = h["data"]
                    ket = ", ".join(x for x in (datagame.kualitas(d), f"Lv.{d['openLevel']}" if d.get("openLevel") else "") if x)
                baris.append(f"{ikon[h['jenis']]} {html.escape(h['nama'])}" + (f" ({ket})" if ket else "")
                             + (f" - {html.escape(h['job'])}" if h.get("job") else ""))
        if hasil[0]["jenis"] in ("enchant", "gem"):
            baris.append("\n<i>Sumber: nama gem dari roworlddb.com; angka & set dari layar Enchant game Anda "
                         "(database_lokal/enchant.json)</i>")
        else:
            baris.append(f"\n<i>Sumber: roworlddb.com (komunitas, server SEA) versi "
                         f"{html.escape(datagame.info_lokal().get('versi', '?'))}</i>")
        teks = "\n".join(baris)
        try:
            ikon = datagame.gambar_ikon(hasil[0])
        except Exception:
            ikon = None
        if ikon and len(teks) <= 1000:  # batas caption foto Telegram
            self.kirim.tambah("balasan", self.tg.kirim_foto, chat_id, ikon, teks, "ikon.png")
        else:
            self.balas(chat_id, teks)

    def loop_database(self) -> None:
        """Sekali sehari cek apakah database di roworlddb.com sudah diperbarui (mis. setelah patch game)."""
        while not self.berhenti.is_set():
            try:
                if datagame.perlu_cek(24):
                    berubah, pesan = datagame.perbarui(log=self.log.info)
                    self.log.info(pesan)
                    if berubah:
                        self.siarkan_teks("📦 " + html.escape(pesan))
            except Exception as e:  # noqa: BLE001
                self.log.warning("Cek pembaruan database gagal (dicoba lagi nanti): %s", e)
            self.berhenti.wait(3600)

    def p_job(self, chat_id, isi):
        daftar = ", ".join(job.daftar_job())
        if not isi.strip():
            sekarang = html.escape(str(self.profil.get("job") or "belum diisi"))
            self.balas(chat_id, f"🧙 Job <b>{self.nama_akun(self.profil)}</b>: <b>{sekarang}</b>\n"
                                f"Ganti: <code>/job Knight</code>\nPilihan: {daftar}")
            return
        nama = job.nama_resmi(isi)
        if not nama:
            self.balas(chat_id, f"Job <b>{html.escape(isi)}</b> tidak dikenal.\nPilihan: {daftar}")
            return
        with self.kunci:
            self.profil["job"] = nama
            self.simpan()
        teks = f"🧙 Job untuk profil <b>{self.nama_aman()}</b> = <b>{nama}</b>"
        ikon = getattr(self, "ikon_terakhir", None)
        if ikon is not None and time.time() - getattr(self, "ikon_waktu", 0) <= self.JOB_BERLAKU:
            # Ingat ikon asli dari game ini sebagai contoh job tsb, supaya berikutnya langsung kenal.
            job.ajarkan(nama, ikon)
            self.job_terakhir, self.job_waktu = job.HasilJob(nama, True, 1.0, ikon), time.time()
            self.log.info("Ikon job diajarkan: %s", nama)
            teks += "\n✅ Ikon job di game sudah saya ingat. Berikutnya terdeteksi otomatis."
        else:
            teks += ("\n(Ikon job belum terlihat di layar. Biarkan game tampil di HUD biasa ~15 detik, "
                     "lalu ketik /job ini lagi supaya ikonnya saya ingat.)")
        self.balas(chat_id, teks)

    def p_rekam(self, chat_id, isi):
        """Mode train: simpan gambar jendela game tiap kali layar berubah, sampai /stop."""
        if self.rekam is not None and self.rekam.aktif:
            self.balas(chat_id, f"📼 Mode train sudah jalan ({self.rekam.jumlah} gambar). Ketik /stop untuk berhenti.")
            return
        if not str(self.cfg.get("judul_jendela_game") or "").strip() or self.foto_game(None) is None:
            self.balas(chat_id, "⚠️ Jendela game tidak ditemukan (belum dibuka / di-minimize). Buka gamenya dulu.")
            return
        self.rekam = latih.Perekam(lambda: self.foto_game(None))
        self.rekam.mulai_rekam()
        self._pantau_rekam(self.rekam, chat_id)
        self.log.info("Mode train mulai: %s", self.rekam.folder)
        self.balas(chat_id, "📼 <b>Mode train AKTIF</b>\nSilakan buka halaman di game: Enchant (tekan lama tiap gem), "
                            "Insert Card, Character Info > Detailed Stats, Skills, dll.\n"
                            "Gambar hanya disimpan saat layar berubah. Bot tidak menyentuh game.\n"
                            f"Ketik /stop kalau sudah. (Otomatis berhenti setelah {latih.MAKS_MENIT} menit.)")

    def _pantau_rekam(self, rekam: latih.Perekam, chat_id: int) -> None:
        """Kalau rekaman berhenti sendiri (batas waktu / jumlah), tetap diolah dan dikabari."""
        def tunggu():
            rekam._thread.join()
            if not getattr(rekam, "_diolah", False):
                self._selesai_rekam(rekam, chat_id)
        threading.Thread(target=tunggu, daemon=True, name="tunggu-rekam").start()

    def _selesai_rekam(self, rekam: latih.Perekam, chat_id: int) -> None:
        if getattr(rekam, "_diolah", False):
            return
        rekam._diolah = True
        try:
            r = rekam.olah(self.cfg["ocr"])
        except Exception as e:
            self.log.exception("Gagal mengolah rekaman train")
            self.balas(chat_id, f"⚠️ Rekaman tersimpan, tapi gagal diolah: {html.escape(str(e))}")
            return
        hal = "\n".join(f"   • {html.escape(k)}: {v} gambar" for k, v in r["halaman"].items()) or "   (kosong)"
        menit = r["durasi_detik"] // 60
        self.log.info("Mode train selesai: %s gambar, %s", r["jumlah_gambar"], rekam.folder)
        self.balas(chat_id, f"📼 <b>Mode train selesai</b> ({html.escape(r['alasan_berhenti'] or 'dihentikan')})\n"
                            f"⏱ {menit} menit {r['durasi_detik'] % 60} detik, {r['jumlah_gambar']} gambar "
                            f"({latih.ukuran_mb(rekam.folder):.0f} MB)\n{hal}\n"
                            f"📁 <code>data/_latih/{rekam.folder.name}</code>\n"
                            + self.teks_belajar(r.get("belajar") or [], r.get("dibaca_enchant", 0)))

    @staticmethod
    def teks_belajar(baris: list[str], dibaca: int) -> str:
        if baris:
            tampil = baris[:25]
            lebih = f"\n   ... +{len(baris) - 25} lainnya" if len(baris) > 25 else ""
            return ("🧠 <b>Dipelajari otomatis</b> (sudah masuk /db):\n"
                    + "\n".join("   " + html.escape(t) for t in tampil) + lebih)
        if dibaca:
            return f"🧠 {dibaca} layar Enchant terbaca, tidak ada data baru (sudah tercatat semua)."
        return ("ℹ️ Tidak ada layar Enchant yang terbaca. Untuk mengajari bot: buka Enchant, "
                "tekan lama ikon gem (detail gem), dan pilih equipment yang set-nya aktif.")

    def p_rekam_stop(self, chat_id, isi):
        rekam = self.rekam
        if rekam is None or not rekam.aktif:
            self.balas(chat_id, "Mode train tidak sedang jalan. Mulai dengan /record_train")
            return
        rekam.hentikan("dihentikan dengan /stop")
        self.rekam = None
        self.balas(chat_id, f"⏹ Mode train berhenti ({rekam.jumlah} gambar). Sedang dibaca, ringkasan menyusul... "
                            "Pemantauan DPS tetap jalan.")
        # Pengolahan dijalankan oleh _pantau_rekam (yang menunggu perekam selesai), supaya tidak dobel.

    def p_stop(self, chat_id, isi):
        if self.rekam is not None and self.rekam.aktif:
            self.p_rekam_stop(chat_id, isi)  # saat mode train jalan, /stop = matikan mode train saja
            return
        self.jeda = True
        self.balas(chat_id, "⏸ Pemantauan dijeda. Ketik /start untuk lanjut.")

    def p_start(self, chat_id, isi):
        self.jeda = False
        self.acuan_tanpa_hasil, self.sudah_warn_tanpa_hasil = time.time(), False
        self.bangun.set()
        self.balas(chat_id, f"▶️ Pemantauan jalan. Profil: <b>{self.nama_aman()}</b>. Ketik /help untuk perintah.")

    # ------------------------------------------------------------ developer (/update dari jauh)

    def p_dev_mode(self, chat_id, isi):
        pilihan = isi.strip().lower()
        with self.kunci:
            nyala = not self.cfg.get("dev_ikut_laporan", True)
            if pilihan in ("on", "nyala", "1"):
                nyala = True
            elif pilihan in ("off", "mati", "0"):
                nyala = False
            self.cfg["dev_ikut_laporan"] = nyala
            self.simpan()
        self.balas(chat_id, "🛠 Dev mode <b>ON</b>: Anda ikut menerima laporan otomatis (DPS, rapor, ringkasan)."
                   if nyala else
                   "🛠 Dev mode <b>OFF</b>: laporan otomatis hanya ke Philip. Perintah tetap bisa dipakai.")

    def p_data_latih(self, chat_id, isi):
        """Developer: lihat / ambil gambar Enchant-Gem yang terkumpul otomatis (latih.simpan_otomatis)."""
        hari = latih.info_otomatis()
        tanggal = re.sub(r"\D", "", isi)
        if not tanggal:
            if not hari:
                self.balas(chat_id, "Belum ada data latih otomatis. Terkumpul sendiri saat Philip membuka halaman Enchant/Gem.")
                return
            baris = [f"{t[6:]}/{t[4:6]}: {n} gambar ({mb:.0f} MB)  →  <code>/data_latih {t}</code>"
                     for t, n, mb in hari[:14]]
            self.balas(chat_id, "📚 <b>Data latih otomatis</b>\n" + "\n".join(baris))
            return
        if tanggal not in {t for t, _, _ in hari}:
            self.balas(chat_id, f"Tidak ada data tanggal {html.escape(tanggal)}. Ketik /data_latih untuk daftarnya.")
            return
        isi_zip, masuk, total = latih.zip_otomatis(tanggal)
        ket = f"📚 Data latih {tanggal}: {masuk}/{total} gambar" + (" (sisanya kebesaran untuk Telegram)" if masuk < total else "")
        self.kirim.tambah("data latih", self.tg.kirim_dokumen, chat_id, isi_zip, f"latih_{tanggal}.zip", ket)

    def p_log(self, chat_id, isi):
        try:
            n = max(5, min(300, int(isi))) if isi.strip() else 40
        except ValueError:
            n = 40
        try:
            baris = (umum.FOLDER_LOG / "bot.log").read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        except OSError as e:
            self.balas(chat_id, f"Log tidak terbaca: {html.escape(str(e))}")
            return
        teks = self.tg._bersih("\n".join(baris))
        if len(teks) > 3800:
            self.kirim.tambah("log", self.tg.kirim_dokumen, chat_id, teks.encode("utf-8"), "bot_log.txt",
                              f"📄 {n} baris terakhir log bot")
        else:
            self.balas(chat_id, f"<pre>{html.escape(teks) or '(kosong)'}</pre>")

    def p_restart(self, chat_id, isi):
        self._restart(chat_id, "🔄 Bot restart... menyala lagi ±15 detik.", {"jenis": "restart"})

    def _restart(self, chat_id: int, teks: str, tanda: dict) -> None:
        """Simpan tanda (supaya setelah menyala bot lapor), lalu keluar dengan KODE_RESTART.
        4_jalankan_bot.bat otomatis menyalakan bot lagi (jaga_bot.ps1 juga, paling lambat 5 menit)."""
        tanda.update(chat_id=chat_id, waktu=datetime.now().strftime("%d/%m %H:%M:%S"))
        try:
            umum.FOLDER_LOG.mkdir(exist_ok=True)
            FILE_TANDA_UPDATE.write_text(json.dumps(tanda, ensure_ascii=False), encoding="utf-8")
        except OSError:
            self.log.exception("Gagal menulis tanda update")
        try:
            self.tg.kirim_teks(chat_id, teks)
        except Exception:
            pass
        self.log.info("Restart diminta developer (%s).", tanda.get("jenis"))
        time.sleep(2)  # beri waktu antrean kirim
        os._exit(KODE_RESTART)

    def p_matikan(self, chat_id, isi):
        """Matikan bot sepenuhnya atas kemauan sendiri. Perlu konfirmasi supaya tidak kepencet."""
        if isi.strip().lower() not in ("ya", "y", "yes", "yakin"):
            self.balas(chat_id, "⚠️ Bot akan MATI total dan tidak menyala sendiri lagi.\n"
                                "Menyala lagi kalau laptop di-restart, atau buka <code>4_jalankan_bot.bat</code>.\n"
                                "Cuma mau jeda sebentar? Pakai /stop.\n\nYakin? Ketik <code>/matikan ya</code>")
            return
        try:
            FILE_DIMATIKAN.write_text(f"Dimatikan lewat Telegram {datetime.now():%d/%m/%Y %H:%M:%S} oleh {chat_id}\n"
                                      "Hapus file ini atau buka 4_jalankan_bot.bat untuk menyalakan lagi.\n",
                                      encoding="utf-8")
        except OSError as e:
            self.balas(chat_id, f"Gagal mematikan: {html.escape(str(e))}")
            return
        self.log.info("Bot dimatikan lewat Telegram oleh %s.", chat_id)
        teks = "⏹ Bot dimatikan. Menyala lagi saat laptop restart, atau buka <code>4_jalankan_bot.bat</code>"
        for cid in self.penerima:
            try:
                self.tg.kirim_teks(cid, teks)
            except Exception:
                pass
        time.sleep(1)
        os._exit(0)  # kode 0 = 4_jalankan_bot.bat tidak mengulang

    def _lapor_setelah_restart(self) -> None:
        try:
            data = json.loads(FILE_TANDA_UPDATE.read_text(encoding="utf-8"))
            FILE_TANDA_UPDATE.unlink()
        except (OSError, ValueError):
            return
        dev = int(data["chat_id"]) if data.get("chat_id") else None
        if data.get("jenis") == "restart":
            if dev:
                self.balas(dev, "✅ Bot sudah menyala lagi setelah restart.")
            return
        # Philip cukup 1 baris; developer dapat daftar file.
        judul = "↩️ Update dibatalkan" if data.get("jenis") == "batal" else "🔧 Bot diperbarui"
        for cid in self.chat_ids:
            if cid != dev:
                self.balas(cid, f"{judul}, sudah aktif lagi.")
        if dev:
            daftar = "\n".join(f"• <code>{html.escape(p)}</code>" for p in data.get("file", [])[:30])
            self.balas(dev, f"{judul} ({html.escape(data.get('waktu', ''))}):\n{daftar}")

    @staticmethod
    def _baca_berkas_update(nama: str, isi: bytes) -> tuple[dict[str, bytes], list[str]]:
        """-> (file yang akan dipasang {path relatif: isi}, file yang dilewati). ValueError kalau ditolak."""
        if nama.lower().endswith(".zip"):
            try:
                zf = zipfile.ZipFile(io.BytesIO(isi))
                mentah = {i.filename.replace("\\", "/"): zf.read(i) for i in zf.infolist() if not i.is_dir()}
            except (zipfile.BadZipFile, OSError) as e:
                raise ValueError(f"file .zip rusak ({e})") from None
            # Zip berisi satu folder induk (mis. ROPython/bot.py) -> buang folder induknya.
            akar = {p.split("/", 1)[0] for p in mentah}
            if len(akar) == 1 and all("/" in p for p in mentah) and not (umum.FOLDER / next(iter(akar))).is_dir():
                mentah = {p.split("/", 1)[1]: d for p, d in mentah.items()}
        else:
            mentah = {nama: isi}
        berkas, dilewati = {}, []
        for p, data in mentah.items():
            bagian = [b for b in p.split("/") if b]
            if not bagian or p.startswith("/") or ":" in p or ".." in bagian:
                raise ValueError(f"nama file tidak aman: {p}")
            if "__pycache__" in bagian or p.lower().endswith(".pyc"):
                continue
            if bagian[0].lower() in DILARANG_UPDATE:
                dilewati.append(p)
                continue
            p = "/".join(bagian)
            if p.lower().endswith(".py"):
                try:
                    compile(data.decode("utf-8-sig"), p, "exec")
                except UnicodeDecodeError:
                    raise ValueError(f"{p} bukan teks UTF-8") from None
                except SyntaxError as e:
                    raise ValueError(f"{p} salah tulis di baris {e.lineno}: {e.msg}") from None
            elif p.lower().endswith(".json"):
                try:
                    json.loads(data.decode("utf-8-sig"))
                except ValueError as e:
                    raise ValueError(f"{p} bukan JSON yang benar: {e}") from None
            berkas[p] = data
        if not berkas:
            raise ValueError("tidak ada file yang boleh dipasang"
                             + (f" (dilewati: {', '.join(dilewati)})" if dilewati else ""))
        return berkas, dilewati

    @staticmethod
    def _pulihkan(cadangan) -> list[str]:
        """Kembalikan file dari folder cadangan. -> daftar file yang dipulihkan/dihapus."""
        info = json.loads((cadangan / "_info_update.json").read_text(encoding="utf-8"))
        for p in info.get("diganti", []):
            shutil.copy2(cadangan / p, umum.FOLDER / p)
        for p in info.get("baru", []):
            try:
                (umum.FOLDER / p).unlink()
            except FileNotFoundError:
                pass
        return info.get("diganti", []) + info.get("baru", [])

    def p_update(self, chat_id, isi, pesan):
        if isi.strip().lower() in ("batal", "undo", "rollback"):
            self._update_batal(chat_id)
            return
        dok = pesan.get("document") or (pesan.get("reply_to_message") or {}).get("document")
        grup = pesan.get("media_group_id") if pesan.get("document") else None
        if grup:
            # Beberapa file dikirim sekaligus (album): file lain di album datang sebagai pesan terpisah.
            # Tunggu sebentar di thread lain supaya semuanya terkumpul, lalu pasang SEKALI + restart sekali.
            def nanti():
                time.sleep(4)
                with self.kunci:
                    dok_grup = [d for w, g, d in self.dok_tunggu.get(chat_id, []) if g == grup]
                self._pasang_update(chat_id, dok_grup or [dok])
            threading.Thread(target=nanti, daemon=True, name="update").start()
            return
        if dok:
            self._pasang_update(chat_id, [dok])
            return
        # "/update" diketik sendiri: pakai semua file yang barusan dikirim (10 menit terakhir).
        with self.kunci:
            dok_tunggu = [d for w, g, d in self.dok_tunggu.get(chat_id, []) if time.time() - w <= 600]
        if dok_tunggu:
            self._pasang_update(chat_id, dok_tunggu)
            return
        self.balas(chat_id, "Kirim file .py / .zip (boleh beberapa sekaligus) dengan caption <code>/update</code>, "
                            "atau kirim filenya dulu lalu ketik /update.\n\n" + BANTUAN_DEV)

    def _pasang_update(self, chat_id, daftar_dok: list[dict]) -> None:
        if not self.kunci_update.acquire(blocking=False):
            self.balas(chat_id, "⏳ Update lain sedang diproses, tunggu sebentar.")
            return
        try:
            self._pasang_update_isi(chat_id, daftar_dok)
        finally:
            self.kunci_update.release()

    def _pasang_update_isi(self, chat_id, daftar_dok: list[dict]) -> None:
        # File yang sama dikirim 2x: pakai yang terakhir.
        unik = {}
        for d in daftar_dok:
            unik[os.path.basename(d.get("file_name") or "file")] = d
        with self.kunci:  # yang sudah dipakai dibuang dari antrean
            pakai = {d.get("file_unique_id") for d in daftar_dok}
            self.dok_tunggu[chat_id] = [x for x in self.dok_tunggu.get(chat_id, [])
                                        if x[2].get("file_unique_id") not in pakai]
        if any((d.get("file_size") or 0) > 20_000_000 for d in unik.values()):
            self.balas(chat_id, "❌ Ada file terlalu besar (maks 20 MB). Kirim hanya file yang diubah saja.")
            return
        self.balas(chat_id, f"⏳ Mengunduh & mengecek {len(unik)} file: "
                            + ", ".join(f"<code>{html.escape(n)}</code>" for n in unik) + "...")
        berkas, dilewati, nama = {}, [], ", ".join(unik)
        for n, dok in unik.items():
            try:
                info = self.tg.panggil("getFile", {"file_id": dok["file_id"]})
                r = requests.get(f"https://api.telegram.org/file/bot{self.tg.token}/{info['file_path']}",
                                 timeout=120)
                r.raise_for_status()
                isi_file = r.content
            except Exception as e:
                self.balas(chat_id, f"❌ Gagal mengunduh {html.escape(n)}: {html.escape(self.tg._bersih(str(e)))}\n"
                                    "Tidak ada yang diubah.")
                return
            try:
                b, lewat = self._baca_berkas_update(n, isi_file)
            except ValueError as e:
                self.balas(chat_id, f"❌ Update ditolak, tidak ada yang diubah.\n{html.escape(str(e))}")
                return
            berkas.update(b)
            dilewati += lewat

        self._terapkan_berkas_update(chat_id, berkas, dilewati, nama)

    def _terapkan_berkas_update(self, chat_id, berkas: dict[str, bytes], dilewati: list[str],
                                nama: str, setelah_ok=None) -> bool:
        """1) Cadangan file lama, 2) pasang file baru, 3) uji 'import bot', gagal -> pulihkan, sukses -> restart."""
        cadangan = umum.FOLDER / "cadangan_update" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        diganti = [p for p in berkas if (umum.FOLDER / p).exists()]
        baru = [p for p in berkas if p not in diganti]
        try:
            for p in diganti:
                (cadangan / p).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(umum.FOLDER / p, cadangan / p)
            cadangan.mkdir(parents=True, exist_ok=True)
            (cadangan / "_info_update.json").write_text(
                json.dumps({"diganti": diganti, "baru": baru, "dari": nama}, ensure_ascii=False), encoding="utf-8")
            for p, data in berkas.items():
                tujuan = umum.FOLDER / p
                tujuan.parent.mkdir(parents=True, exist_ok=True)
                sementara = tujuan.with_name(tujuan.name + ".baru")
                sementara.write_bytes(data)
                os.replace(sementara, tujuan)
        except OSError as e:
            try:
                self._pulihkan(cadangan)
            except Exception:
                self.log.exception("Gagal memulihkan cadangan %s", cadangan)
            if chat_id:
                self.balas(chat_id, f"❌ Gagal menulis file ({html.escape(str(e))}). File lama dikembalikan.")
            return False

        try:
            uji = subprocess.run([sys.executable, "-c", "import bot"], cwd=str(umum.FOLDER), capture_output=True,
                                 timeout=180, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            gagal = uji.stderr.decode("utf-8", "replace") if uji.returncode != 0 else ""
        except Exception as e:
            gagal = f"{type(e).__name__}: {e}"
        if gagal:
            self._pulihkan(cadangan)
            info = json.loads((cadangan / "_info_update.json").read_text(encoding="utf-8"))
            info["dibatalkan"] = True
            (cadangan / "_info_update.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
            if chat_id:
                self.balas(chat_id, "❌ Kode baru error saat dicoba, file lama sudah dikembalikan (bot tidak restart).\n"
                                    f"<pre>{html.escape(gagal[-1500:])}</pre>")
            return False

        # Simpan 10 cadangan terakhir saja.
        semua = sorted(d for d in cadangan.parent.iterdir() if d.is_dir())
        for lama in semua[:-10]:
            shutil.rmtree(lama, ignore_errors=True)

        if setelah_ok:
            try:
                setelah_ok()
            except Exception:
                pass

        teks = (f"✅ Lolos cek ({html.escape(nama)}). {len(berkas)} file dipasang:\n"
                + "\n".join(f"• <code>{html.escape(p)}</code>{' (baru)' if p in baru else ''}" for p in berkas)
                + (f"\n⚠️ Dilewati (data/config, tidak boleh ditimpa): {html.escape(', '.join(dilewati))}"
                   if dilewati else "")
                + "\n🔄 Restart... menyala lagi ±15 detik. Batalkan: /update batal")
        target_cid = chat_id or (next(iter(self.dev_ids), None))
        self._restart(target_cid, teks, {"jenis": "update", "file": list(berkas)})
        return True

    def p_auto_update(self, chat_id, isi: str) -> None:
        """Kelola auto-update dari GitHub: status, set repo/branch/token, on/off, atau cek sekarang."""
        isi = isi.strip()
        au = dict(self.cfg.get("auto_update") or {})
        if not isi:
            info = autoupdate.info_config(self.cfg)
            sha = autoupdate.sha_lokal()
            self.balas(chat_id,
                       "🔄 <b>Auto-Update GitHub</b>\n"
                       f"• Status: <b>{'AKTIF' if info['aktif'] and info['repo'] else 'MATI'}</b>\n"
                       f"• Repo: <code>{html.escape(info['repo'] or '(belum diatur)')}</code> (branch: <code>{html.escape(info['branch'])}</code>)\n"
                       f"• Token private: {'✅ terpasang' if info['token'] else '— (repo publik)'}\n"
                       f"• Cek tiap: {info['interval_menit']} menit\n"
                       f"• Commit terakhir: <code>{html.escape(sha[:10] if sha else '-')}</code>\n\n"
                       "Perintah:\n"
                       "• <code>/auto_update owner/repo</code> (atau + branch)\n"
                       "• <code>/auto_update token ghp_...</code> (untuk repo private)\n"
                       "• <code>/auto_update cek</code> (tarik update sekarang)\n"
                       "• <code>/auto_update on</code> / <code>off</code>")
            return
        bag = isi.split()
        cmd = bag[0].lower()
        if cmd in ("cek", "now", "tarik"):
            threading.Thread(target=self._cek_auto_update, args=(chat_id, True), daemon=True, name="auto-update-now").start()
            return
        if cmd in ("on", "off"):
            with self.kunci:
                au["aktif"] = (cmd == "on")
                self.cfg["auto_update"] = au
                self.simpan()
            self.balas(chat_id, f"✅ Auto-update {'diaktifkan' if au['aktif'] else 'dimatikan'}.")
            return
        if cmd == "token":
            tok = bag[1].strip() if len(bag) > 1 else ""
            with self.kunci:
                au["token"] = "" if tok.lower() in ("hapus", "clear", "-") else tok
                self.cfg["auto_update"] = au
                self.simpan()
            self.balas(chat_id, "✅ Token GitHub disimpan di config." if au["token"] else "✅ Token GitHub dihapus.")
            return
        if "/" in bag[0]:
            with self.kunci:
                au["repo"] = bag[0].strip().strip("/")
                if len(bag) > 1:
                    au["branch"] = bag[1].strip()
                au.setdefault("branch", "main")
                au.setdefault("interval_menit", 15)
                au["aktif"] = True
                self.cfg["auto_update"] = au
                self.simpan()
            self.balas(chat_id, f"✅ Repo auto-update diatur ke <code>{html.escape(au['repo'])}</code> "
                                f"(branch <code>{html.escape(au['branch'])}</code>) dan AKTIF.\n"
                                "Ketik <code>/auto_update cek</code> untuk langsung menarik update pertama.")
            return
        self.balas(chat_id, "Format: <code>/auto_update owner/repo [branch]</code>, "
                            "<code>/auto_update cek</code>, <code>/auto_update token ...</code>, atau <code>on/off</code>.")

    def _cek_auto_update(self, chat_id=None, paksa_kabar: bool = False) -> None:
        info = autoupdate.info_config(self.cfg)
        if not info["repo"]:
            if paksa_kabar and chat_id:
                self.balas(chat_id, "⚠️ Repo GitHub belum diatur. Ketik <code>/auto_update owner/repo</code> dulu.")
            return
        if not paksa_kabar and not info["aktif"]:
            return
        if not self.kunci_update.acquire(blocking=False):
            if paksa_kabar and chat_id:
                self.balas(chat_id, "⏳ Update lain sedang diproses.")
            return
        try:
            sha_baru, pesan = autoupdate.cek_commit_terbaru(info["repo"], info["branch"], info["token"])
            sha_lama = autoupdate.sha_lokal()
            if sha_baru == sha_lama:
                if paksa_kabar and chat_id:
                    self.balas(chat_id, f"✅ Sudah versi terbaru (<code>{sha_baru[:8]}</code> — {html.escape(pesan)}).")
                return
            if paksa_kabar and chat_id:
                self.balas(chat_id, f"⏳ Ditemukan commit baru <code>{sha_baru[:8]}</code> ({html.escape(pesan)}), mengunduh...")
            berkas, dilewati = autoupdate.unduh_berkas_berubah(
                info["repo"], info["branch"], info["token"], DILARANG_UPDATE)
            if not berkas:
                autoupdate.simpan_sha(sha_baru)
                if paksa_kabar and chat_id:
                    self.balas(chat_id, f"✅ Commit <code>{sha_baru[:8]}</code> tidak mengubah file bot (SHA dicatat).")
                return
            sumber = f"GitHub {info['repo']}@{sha_baru[:8]} ({pesan})"
            self._terapkan_berkas_update(chat_id, berkas, dilewati, sumber,
                                         setelah_ok=lambda: autoupdate.simpan_sha(sha_baru))
        except Exception as e:
            self.log.warning("Auto-update gagal: %s", e)
            if paksa_kabar and chat_id:
                self.balas(chat_id, f"❌ Auto-update gagal: {html.escape(str(e))}")
        finally:
            self.kunci_update.release()

    def loop_auto_update(self) -> None:
        """Cek commit baru di GitHub secara berkala bila auto_update.repo diatur & aktif."""
        time.sleep(45)  # beri jeda setelah startup
        while not self.berhenti.is_set():
            try:
                self._cek_auto_update(chat_id=None, paksa_kabar=False)
            except Exception:
                self.log.exception("Error di loop auto_update")
            menit = autoupdate.info_config(self.cfg)["interval_menit"]
            self.berhenti.wait(menit * 60)

    def _update_batal(self, chat_id):
        folder = umum.FOLDER / "cadangan_update"
        calon = []
        if folder.is_dir():
            for d in sorted(folder.iterdir(), reverse=True):
                f = d / "_info_update.json"
                try:
                    if not json.loads(f.read_text(encoding="utf-8")).get("dibatalkan"):
                        calon.append(d)
                except (OSError, ValueError):
                    continue
        if not calon:
            self.balas(chat_id, "Tidak ada update yang bisa dibatalkan.")
            return
        d = calon[0]
        try:
            file = self._pulihkan(d)
            info = json.loads((d / "_info_update.json").read_text(encoding="utf-8"))
            info["dibatalkan"] = True
            (d / "_info_update.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            self.balas(chat_id, f"❌ Gagal membatalkan: {html.escape(str(e))}")
            return
        self._restart(chat_id, f"↩️ Update {d.name} dibatalkan ({len(file)} file). Restart...",
                      {"jenis": "batal", "file": file})

    # ------------------------------------------------------------ mulai

    def jalankan(self) -> None:
        FILE_DIMATIKAN.unlink(missing_ok=True)  # dinyalakan lagi = penjaga boleh menjaga lagi
        self.kirim.start()
        threading.Thread(target=self.loop_perintah, daemon=True, name="perintah").start()
        threading.Thread(target=self.loop_database, daemon=True, name="database").start()
        threading.Thread(target=self.loop_harian, daemon=True, name="harian").start()
        threading.Thread(target=self.loop_auto_update, daemon=True, name="auto-update").start()
        catatan.sesi_mulai(self.pid)
        # Menu "/" di Telegram = hanya perintah yang dipakai (yang lama ikut hilang dari menu).
        self.kirim.tambah("menu perintah", self.tg.panggil, "setMyCommands",
                          {"commands": json.dumps([{"command": c, "description": d} for c, d in MENU])})
        if FILE_TANDA_UPDATE.exists():
            self._lapor_setelah_restart()  # restart dari developer: cukup kabar 1 baris
        else:
            self.siarkan_teks(f"✅ Bot pemantau DPS aktif.\n👤 Karakter aktif: <b>{self.nama_akun(self.profil)}</b>"
                              f"{self.teks_karakter(self.profil, False)}\n"
                              f"🎯 Target: {umum.fmt(self.profil.get('target'))}\n"
                              "Ketik /help untuk daftar perintah.")
        self.log.info("Bot jalan. Profil '%s'. Jendela ini boleh di-minimize. Ctrl+C untuk berhenti.",
                      self.profil["nama"])
        try:
            self.loop_pantau()
        except KeyboardInterrupt:
            self.log.info("Bot dihentikan.")
            self.berhenti.set()


def main() -> int:
    umum.siapkan_konsol()
    umum.aktifkan_dpi_aware()
    try:
        cfg = umum.muat_config()
    except umum.ConfigError as e:
        print("MASALAH CONFIG:", e)
        return 2
    token = str(cfg["telegram"].get("token", "")).strip()
    if not token or token == umum.TOKEN_KOSONG:
        print("Token bot belum diisi. Buka config.json, isi \"token\" dengan token dari @BotFather.")
        return 2
    ids = cfg["telegram"].get("chat_id_diizinkan")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids) or ids == [123456789]:
        print("chat_id belum diisi. Jalankan 5_cek_chat_id.bat, lalu isi \"chat_id_diizinkan\" di config.json.")
        print("Contoh: \"chat_id_diizinkan\": [987654321]   (angka, tanpa tanda kutip)")
        return 2
    if cfg.get("mode") not in ("target", "perubahan"):
        cfg["mode"] = "perubahan"

    log = umum.siapkan_log("bot", token)
    tg = Telegram(token)
    try:
        info = tg.info_bot()
        log.info("Terhubung sebagai bot @%s", info.get("username"))
    except TelegramError as e:
        print(f"Token ditolak Telegram ({e}). Cek lagi token di config.json.")
        return 2
    except TelegramSementara as e:
        log.warning("Internet belum tersambung (%s). Bot tetap jalan dan mencoba terus.", e)
    Bot(cfg, tg, log).jalankan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
