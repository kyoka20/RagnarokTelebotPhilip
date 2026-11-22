"""Pencatatan: CSV per profil + penanda awal sesi (untuk /laporan)."""
from __future__ import annotations

import csv
import json
import threading
from datetime import datetime
from pathlib import Path

import umum

KOLOM = ["waktu", "status", "dps", "total_dmg", "rekor", "gambar", "keterangan"]
FORMAT_WAKTU = "%Y-%m-%d %H:%M:%S"
_kunci = threading.Lock()


def folder_profil(pid: str) -> Path:
    f = umum.FOLDER_DATA / pid
    (f / "gambar").mkdir(parents=True, exist_ok=True)
    return f


def file_csv(pid: str) -> Path:
    return folder_profil(pid) / "riwayat.csv"


def tambah(pid: str, status: str, dps=None, total=None, rekor=None, gambar: str = "",
           keterangan: str = "", waktu: datetime | None = None) -> None:
    """status: 'ok' (berhasil baca) atau 'gagal'."""
    f = file_csv(pid)
    waktu = waktu or datetime.now()
    with _kunci:
        baru = not f.exists()
        with f.open("a", newline="", encoding="utf-8-sig") as fh:
            tulis = csv.writer(fh)
            if baru:
                tulis.writerow(KOLOM)
            tulis.writerow([waktu.strftime(FORMAT_WAKTU), status,
                            "" if dps is None else dps, "" if total is None else total,
                            "" if rekor is None else rekor, gambar, keterangan])


def baca_ok(pid: str, sejak: datetime | None = None) -> list[dict]:
    """Semua baris yang berhasil dibaca, urut dari yang paling lama."""
    f = file_csv(pid)
    if not f.exists():
        return []
    hasil = []
    with _kunci:
        with f.open(newline="", encoding="utf-8-sig") as fh:
            for baris in csv.DictReader(fh):
                try:
                    if baris.get("status") != "ok" or not baris.get("dps"):
                        continue
                    waktu = datetime.strptime(baris["waktu"], FORMAT_WAKTU)
                    if sejak and waktu < sejak:
                        continue
                    hasil.append({
                        "waktu": waktu,
                        "dps": int(baris["dps"]),
                        "total": int(baris["total_dmg"]) if baris.get("total_dmg") else None,
                        "rekor": int(baris["rekor"]) if baris.get("rekor") else None,
                        "gambar": baris.get("gambar") or "",
                    })
                except (ValueError, KeyError):
                    continue  # baris rusak (mis. diedit manual) dilewati saja
    return hasil


def pindah_hasil(asal: str, tujuan: str, waktu: str) -> dict | None:
    """Pindahkan satu hasil (baris CSV + fotonya) dari profil `asal` ke `tujuan`.
    `waktu` = isi kolom waktu persis (format FORMAT_WAKTU). Hasil: baris yang dipindah, atau None."""
    f_asal, f_tujuan = file_csv(asal), file_csv(tujuan)
    with _kunci:
        if not f_asal.exists():
            return None
        with f_asal.open(newline="", encoding="utf-8-sig") as fh:
            semua = list(csv.DictReader(fh))
        pindah = next((b for b in reversed(semua) if b.get("waktu") == waktu and b.get("status") == "ok"), None)
        if pindah is None:
            return None
        sisa = [b for b in semua if b is not pindah]
        with f_asal.open("w", newline="", encoding="utf-8-sig") as fh:
            tulis = csv.DictWriter(fh, fieldnames=KOLOM, extrasaction="ignore")
            tulis.writeheader()
            tulis.writerows(sisa)
        tujuan_semua = []
        if f_tujuan.exists():
            with f_tujuan.open(newline="", encoding="utf-8-sig") as fh:
                tujuan_semua = list(csv.DictReader(fh))
        tujuan_semua.append(pindah)
        tujuan_semua.sort(key=lambda b: b.get("waktu") or "")
        with f_tujuan.open("w", newline="", encoding="utf-8-sig") as fh:
            tulis = csv.DictWriter(fh, fieldnames=KOLOM, extrasaction="ignore")
            tulis.writeheader()
            tulis.writerows(tujuan_semua)
    gambar = pindah.get("gambar")
    if gambar:
        src = folder_profil(asal) / "gambar" / gambar
        if src.exists():
            src.replace(folder_profil(tujuan) / "gambar" / gambar)
    # Sesi tujuan harus mencakup hasil ini, supaya ikut jadi pembanding / rapor.
    try:
        w = datetime.strptime(waktu, FORMAT_WAKTU)
        if sesi_mulai(tujuan) > w:
            _file_sesi(tujuan).write_text(json.dumps({"mulai": waktu}), encoding="utf-8")
    except ValueError:
        pass
    return pindah


def _file_sesi(pid: str) -> Path:
    return folder_profil(pid) / "sesi.json"


def sesi_mulai(pid: str) -> datetime:
    """Kapan sesi profil ini dimulai. Kalau belum ada, mulai sekarang."""
    f = _file_sesi(pid)
    try:
        return datetime.strptime(json.loads(f.read_text(encoding="utf-8"))["mulai"], FORMAT_WAKTU)
    except Exception:
        return sesi_baru(pid)


def sesi_baru(pid: str) -> datetime:
    sekarang = datetime.now().replace(microsecond=0)
    _file_sesi(pid).write_text(json.dumps({"mulai": sekarang.strftime(FORMAT_WAKTU)}), encoding="utf-8")
    return sekarang
