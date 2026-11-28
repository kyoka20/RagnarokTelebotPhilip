"""Hal-hal umum: lokasi file, config, log, DPI awareness.

Dipakai oleh semua script lain. Tidak ada kode yang menyentuh game di sini.
"""
from __future__ import annotations

import copy
import ctypes
import json
import logging
import os
import re
import shutil
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
FILE_CONFIG = FOLDER / "config.json"
FILE_CONTOH = FOLDER / "config.example.json"
FOLDER_DATA = FOLDER / "data"
FOLDER_LOG = FOLDER / "log"

TOKEN_KOSONG = "ISI_TOKEN_DARI_BOTFATHER"

PROFIL_DEFAULT = {
    "nama": "Akun 1",
    "target": 3000000,
    "label": "DMG Per Second",
    "area": None,
    "nick": "",
    "job": "",
    "id_game": "",
    "kontak": "",     # data pembeli jasa (diisi lewat /input)
    "paket": "",
    "bayar": "",
    "catatan": "",
    "tanggal_order": "",
}

CONFIG_DEFAULT = {
    "telegram": {"token": TOKEN_KOSONG, "chat_id_diizinkan": []},
    "profil_aktif": "akun1",
    "mode": "perubahan",
    "interval_detik": 1,
    "rapor_catatan_kaki": "",
    "judul_jendela_game": "Ragnarok: The New World",
    "kirim_layar_penuh": False,
    "peringatan_gagal_berturut": 0,
    "peringatan_tanpa_hasil_menit": 0,
    "jeda_istirahat_menit": 30,  # /hari: jeda antar test lebih dari ini = istirahat (tidak dihitung)
    # Sasaran di Damage Challenge (dipastikan pemilik 21/11/2026). Dipakai untuk menilai stat/kartu terpakai.
    "sasaran_test": {"nama": "Damage Test Dummy (Humanoid, Medium)", "ras": "Human", "ukuran": "Medium",
                     "elemen": "Neutral"},
    "rapor_otomatis_saat_target": True,  # target tembus -> gambar rapor langsung dikirim
    "ringkasan_harian_jam": "23:30",  # ringkasan hari ini + tagihan dikirim otomatis jam segini ("" = mati)
    "saran_otomatis": True,  # saran singkat di tiap laporan DPS (naik/turun nyata, lama tidak naik, dll)
    "afk_menit": 5,  # /hari: tidak menyentuh jendela game lebih dari ini = AFK, dipotong (0 = mati)
    "ocr": {
        "mesin": "auto",
        "bahasa": "en-US",
        "perbesar": 2,
        "ambang": 190,
        "tesseract_path": "",
    },
    "profil": {"akun1": copy.deepcopy(PROFIL_DEFAULT)},
}

_kunci_config = threading.RLock()


class ConfigError(Exception):
    """Config salah / belum diisi. Pesannya ditampilkan apa adanya ke user."""


def siapkan_konsol() -> None:
    """Supaya huruf/simbol aneh tidak bikin script crash di jendela CMD."""
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def aktifkan_dpi_aware() -> None:
    """Wajib dipanggil paling awal.

    Tanpa ini, kalau Windows display scaling bukan 100% (mis. 125%/150%),
    koordinat mouse dan koordinat screenshot jadi tidak cocok.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _gabung(dasar: dict, isi: dict) -> dict:
    """Isi kunci yang belum ada di `isi` dengan nilai dari `dasar`."""
    hasil = copy.deepcopy(dasar)
    for k, v in isi.items():
        if isinstance(v, dict) and isinstance(hasil.get(k), dict) and k != "profil":
            hasil[k] = _gabung(hasil[k], v)
        else:
            hasil[k] = v
    return hasil


def muat_config() -> dict:
    with _kunci_config:
        if not FILE_CONFIG.exists():
            if FILE_CONTOH.exists():
                shutil.copy(FILE_CONTOH, FILE_CONFIG)
            else:
                simpan_config(copy.deepcopy(CONFIG_DEFAULT))
        try:
            isi = json.loads(FILE_CONFIG.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise ConfigError(
                f"config.json rusak (baris {e.lineno}, kolom {e.colno}): {e.msg}.\n"
                "Biasanya karena kurang koma, kurang tanda kutip, atau ada koma berlebih."
            ) from None
        cfg = _gabung(CONFIG_DEFAULT, isi)
        if not cfg.get("profil"):
            cfg["profil"] = {"akun1": copy.deepcopy(PROFIL_DEFAULT)}
        for pid, p in list(cfg["profil"].items()):
            cfg["profil"][pid] = _gabung(PROFIL_DEFAULT, p)
        if cfg["profil_aktif"] not in cfg["profil"]:
            cfg["profil_aktif"] = next(iter(cfg["profil"]))
        return cfg


def simpan_config(cfg: dict) -> None:
    """Tulis ke file sementara dulu lalu ganti, supaya config tidak rusak kalau listrik mati."""
    with _kunci_config:
        sementara = FILE_CONFIG.with_suffix(".json.tmp")
        sementara.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(sementara, FILE_CONFIG)


def id_profil(nama: str) -> str:
    """'Budi Knight #2' -> 'budi_knight_2' (aman untuk nama folder)."""
    pid = re.sub(r"[^a-z0-9]+", "_", nama.strip().lower()).strip("_")
    return pid[:40] or "profil"


def area_valid(area) -> bool:
    return (
        isinstance(area, dict)
        and all(isinstance(area.get(k), int) for k in ("left", "top", "width", "height"))
        and area["width"] >= 10
        and area["height"] >= 10
    )


def fmt(n) -> str:
    """2717924 -> '2.717.924'"""
    if n is None:
        return "-"
    return f"{int(n):,}".replace(",", ".")


def fmt_selisih(n: int) -> str:
    return ("+" if n >= 0 else "-") + fmt(abs(n))


class _SaringToken(logging.Filter):
    """Jaga-jaga: token bot tidak boleh ikut tertulis di log."""

    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def filter(self, record: logging.LogRecord) -> bool:
        if self.token and self.token != TOKEN_KOSONG:
            pesan = record.getMessage()
            if self.token in pesan:
                record.msg = pesan.replace(self.token, "***TOKEN***")
                record.args = ()
        return True


def siapkan_log(nama: str, token: str = "") -> logging.Logger:
    FOLDER_LOG.mkdir(exist_ok=True)
    log = logging.getLogger(nama)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    bentuk = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    ke_file = RotatingFileHandler(
        FOLDER_LOG / f"{nama}.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    ke_layar = logging.StreamHandler(sys.stdout)
    for h in (ke_file, ke_layar):
        h.setFormatter(bentuk)
        h.addFilter(_SaringToken(token))
        log.addHandler(h)
    return log
