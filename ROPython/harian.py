"""Ringkasan harian: berapa lama Anda bekerja (test DPS) dalam satu hari.

Cara hitung:
- Bot mencatat jam SELESAI tiap test (saat layar hasil muncul). Lama test-nya
  = Total DMG / DPS (biasanya ~2 menit), jadi jam MULAI test juga diketahui.
- Test-test yang jaraknya berdekatan digabung jadi satu "sesi kerja".
  Waktu di antara dua test (ganti equip, atur build, dll) ikut dihitung kerja.
- Kalau jarak dari test sebelumnya lebih dari `jeda_istirahat_menit`
  (default 30 menit), dianggap istirahat dan TIDAK dihitung.
- Waktu dibagi ke karakter: jeda sebelum sebuah test + lama test itu
  masuk ke karakter yang dites.
- AFK: kalau lebih dari `afk_menit` (default 5 menit) tidak memakai mouse/keyboard
  di jendela game (diam, atau sedang browsing/YouTube/chat di aplikasi lain),
  waktu itu dicatat di data/afk.csv dan dipotong dari waktu kerja (kecuali saat
  test sedang berjalan). Ini hanya membaca jam idle & judul jendela aktif dari
  Windows, TIDAK menyentuh game.
"""
from __future__ import annotations

import csv
import ctypes
import html
import re
import threading
from datetime import date, datetime, timedelta

import umum

DURASI_DEFAULT = 120  # detik, kalau Total DMG tidak terbaca
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
FILE_AFK = umum.FOLDER_DATA / "afk.csv"
FORMAT_WAKTU = "%Y-%m-%d %H:%M:%S"
_kunci = threading.Lock()


# ------------------------------------------------------------ AFK

class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def detik_diam() -> float | None:
    """Berapa detik mouse/keyboard PC tidak disentuh (dari Windows). None kalau tidak bisa dibaca."""
    try:
        li = _LastInput()
        li.cbSize = ctypes.sizeof(li)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
            return None
        return ((ctypes.windll.kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000
    except Exception:
        return None


def catat_afk(mulai: datetime, selesai: datetime) -> None:
    with _kunci:
        FILE_AFK.parent.mkdir(parents=True, exist_ok=True)
        baru = not FILE_AFK.exists()
        with FILE_AFK.open("a", newline="", encoding="utf-8-sig") as fh:
            tulis = csv.writer(fh)
            if baru:
                tulis.writerow(["mulai", "selesai"])
            tulis.writerow([mulai.strftime(FORMAT_WAKTU), selesai.strftime(FORMAT_WAKTU)])


def baca_afk() -> list[tuple[datetime, datetime]]:
    if not FILE_AFK.exists():
        return []
    hasil = []
    with _kunci:
        with FILE_AFK.open(newline="", encoding="utf-8-sig") as fh:
            for b in csv.DictReader(fh):
                try:
                    hasil.append((datetime.strptime(b["mulai"], FORMAT_WAKTU),
                                  datetime.strptime(b["selesai"], FORMAT_WAKTU)))
                except (ValueError, KeyError, TypeError):
                    continue
    return hasil


def _irisan(a0: datetime, a1: datetime, daftar: list[tuple[datetime, datetime]]) -> float:
    """Berapa detik rentang [a0, a1] tertutup oleh interval-interval di `daftar` (sudah digabung)."""
    if a1 <= a0:
        return 0.0
    return sum(max(0.0, (min(a1, s) - max(a0, m)).total_seconds()) for m, s in daftar)


def _gabung_interval(daftar: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    hasil: list[list[datetime]] = []
    for m, s in sorted(x for x in daftar if x[1] > x[0]):
        if hasil and m <= hasil[-1][1]:
            hasil[-1][1] = max(hasil[-1][1], s)
        else:
            hasil.append([m, s])
    return [(m, s) for m, s in hasil]


def durasi_test(d: dict) -> float:
    """Lama satu test (detik) = Total DMG / DPS."""
    if d.get("total") and d.get("dps"):
        detik = d["total"] / d["dps"]
        if 5 <= detik <= 900:
            return detik
    return DURASI_DEFAULT


def hitung(daftar: list[tuple[str, dict, list[dict]]], tanggal: date, jeda_menit: float = 30,
           afk: list[tuple[datetime, datetime]] | None = None) -> dict:
    """daftar = [(pid, profil, semua hasil ok)]. afk = [(mulai, selesai)] waktu PC tidak disentuh.
    Hasil: blok sesi kerja + total per karakter (waktu AFK sudah dipotong)."""
    afk = _gabung_interval(afk or [])
    acara = []
    for pid, _p, data in daftar:
        for d in data:
            if d["waktu"].date() != tanggal:
                continue
            acara.append({"pid": pid, "mulai": d["waktu"] - timedelta(seconds=durasi_test(d)),
                          "selesai": d["waktu"], "dps": d["dps"]})
    acara.sort(key=lambda a: a["mulai"])

    blok: list[dict] = []
    for a in acara:
        if blok and (a["mulai"] - blok[-1]["selesai"]).total_seconds() <= jeda_menit * 60:
            b = blok[-1]
            b["acara"].append(a)
            b["selesai"] = max(b["selesai"], a["selesai"])
        else:
            blok.append({"mulai": a["mulai"], "selesai": a["selesai"], "acara": [a]})

    per: dict[str, dict] = {}
    for b in blok:
        kursor = b["mulai"]
        b["afk"] = 0.0
        for a in sorted(b["acara"], key=lambda x: x["selesai"]):
            detik = max(0.0, (a["selesai"] - kursor).total_seconds())
            # AFK hanya dipotong dari waktu SEBELUM test (persiapan); saat test berjalan tetap kerja.
            potong = _irisan(kursor, max(kursor, min(a["mulai"], a["selesai"])), afk)
            detik = max(0.0, detik - potong)
            b["afk"] += potong
            kursor = max(kursor, a["selesai"])
            k = per.setdefault(a["pid"], {"detik": 0.0, "test": 0, "awal": a["dps"], "terbaik": a["dps"],
                                          "mulai": a["mulai"]})
            k["detik"] += detik
            k["test"] += 1
            k["terbaik"] = max(k["terbaik"], a["dps"])

    for b in blok:
        b["kerja"] = max(0.0, (b["selesai"] - b["mulai"]).total_seconds() - b["afk"])
    total = sum(b["kerja"] for b in blok)
    total_afk = sum(b["afk"] for b in blok)
    rentang = (blok[-1]["selesai"] - blok[0]["mulai"]).total_seconds() if blok else 0.0
    return {"blok": blok, "per": per, "total": total, "afk": total_afk,
            "istirahat": max(0.0, rentang - total - total_afk), "jumlah_test": len(acara)}


def fmt_durasi(detik: float) -> str:
    menit = int(round(detik / 60))
    if menit < 1:
        return "&lt;1 menit"
    jam, menit = divmod(menit, 60)
    if not jam:
        return f"{menit} menit"
    return f"{jam} jam" + (f" {menit} menit" if menit else "")


def baca_tanggal(isi: str, hari_ini: date | None = None) -> date | None:
    """'' = hari ini, 'kemarin', '-2' (2 hari lalu), '20' (tgl 20), '20/11', '20/11/2026', '2026-11-20'."""
    hari_ini = hari_ini or date.today()
    isi = isi.strip().lower()
    if isi in ("", "ini", "hari ini", "sekarang"):
        return hari_ini
    if isi in ("kemarin", "kmrn", "kmarin"):
        return hari_ini - timedelta(days=1)
    try:
        if re.fullmatch(r"-\d{1,3}", isi):
            return hari_ini - timedelta(days=int(isi[1:]))
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", isi):
            return datetime.strptime(isi, "%Y-%m-%d").date()
        m = re.fullmatch(r"(\d{1,2})(?:[/.-](\d{1,2})(?:[/.-](\d{2,4}))?)?", isi)
        if not m:
            return None
        tgl = int(m.group(1))
        if m.group(2) is None:  # hanya tanggal -> bulan ini, atau bulan lalu kalau belum lewat
            hasil = hari_ini.replace(day=tgl)
            if hasil > hari_ini:
                bulan_lalu = hari_ini.replace(day=1) - timedelta(days=1)
                hasil = bulan_lalu.replace(day=tgl)
            return hasil
        tahun = int(m.group(3)) if m.group(3) else hari_ini.year
        if tahun < 100:
            tahun += 2000
        hasil = date(tahun, int(m.group(2)), tgl)
        if not m.group(3) and hasil > hari_ini:
            hasil = hasil.replace(year=tahun - 1)
        return hasil
    except ValueError:
        return None


def ringkas(daftar: list[tuple[str, dict, list[dict]]], tanggal: date, jeda_menit: float = 30,
            afk: list[tuple[datetime, datetime]] | None = None) -> list[str]:
    """Versi singkat (untuk ringkasan otomatis malam): beberapa baris saja, tanpa penjelasan."""
    r = hitung(daftar, tanggal, jeda_menit, afk)
    if not r["blok"]:
        return []
    profil = {pid: p for pid, p, _ in daftar}

    def nama(pid):
        p = profil.get(pid, {})
        return html.escape(str(p.get("nick") or p.get("nama") or pid))

    blok = r["blok"]
    baris = [f"⏱ Kerja <b>{fmt_durasi(r['total'])}</b> ({blok[0]['mulai']:%H:%M}-{blok[-1]['selesai']:%H:%M})"
             f" · {r['jumlah_test']} test · {len(r['per'])} karakter"
             + (f" · AFK {fmt_durasi(r['afk'])}" if r["afk"] >= 60 else "")]
    # Kenaikan DPS hari ini, 3 terbesar.
    naik = sorted(((k["terbaik"] - k["awal"]) / k["awal"], pid, k)
                  for pid, k in r["per"].items() if k["awal"] and k["terbaik"] > k["awal"])[::-1]
    if naik:
        baris.append("📈 Naik: " + ", ".join(
            f"{nama(pid)} {f'{pct * 100:+.0f}%'}" for pct, pid, k in naik[:3])
            + (f" (dan {len(naik) - 3} lain)" if len(naik) > 3 else ""))
    # Yang tembus target hari ini (sebelumnya belum).
    tembus = [nama(pid) for pid, k in r["per"].items()
              if (t := int(profil.get(pid, {}).get("target") or 0)) and k["terbaik"] >= t > k["awal"]]
    if tembus:
        baris.append("🎯 Tembus target: " + ", ".join(tembus))
    return baris


def teks(daftar: list[tuple[str, dict, list[dict]]], tanggal: date, jeda_menit: float = 30,
         afk: list[tuple[datetime, datetime]] | None = None, afk_menit: float = 5) -> str:
    """Pesan Telegram (HTML) ringkasan satu hari."""
    r = hitung(daftar, tanggal, jeda_menit, afk)
    profil = {pid: p for pid, p, _ in daftar}
    judul_hari = "HARI INI" if tanggal == date.today() else "HARIAN"
    baris = [f"🗓 <b>RINGKASAN {judul_hari}</b> - {HARI[tanggal.weekday()]} {tanggal:%d/%m/%Y}"]
    if not r["blok"]:
        baris.append("\nBelum ada test DPS yang tercatat di hari ini.")
        baris.append("Hari lain: <code>/hari kemarin</code> atau <code>/hari 20/11</code>")
        return "\n".join(baris)

    blok = r["blok"]
    baris += [f"⏱ Total waktu kerja: <b>{fmt_durasi(r['total'])}</b>",
              f"🕒 Mulai {blok[0]['mulai']:%H:%M} - selesai {blok[-1]['selesai']:%H:%M}"]
    if r["afk"] >= 60:
        baris.append(f"💤 AFK di sela kerja: {fmt_durasi(r['afk'])} (dipotong)")
    if r["istirahat"] >= 60:
        baris.append(f"☕ Jeda/istirahat: {fmt_durasi(r['istirahat'])} (tidak dihitung)")
    baris.append(f"⚔️ {r['jumlah_test']} test DPS, {len(r['per'])} karakter")

    baris.append("\n<b>Per karakter</b> (urut paling lama):")
    urut = sorted(r["per"].items(), key=lambda kv: kv[1]["detik"], reverse=True)
    for i, (pid, k) in enumerate(urut, 1):
        p = profil.get(pid, {})
        nama = html.escape(str(p.get("nick") or p.get("nama") or pid))
        job_ = f" ({html.escape(str(p['job']))})" if p.get("job") else ""
        naik = ""
        if k["terbaik"] != k["awal"] and k["awal"]:
            naik = f" ({(k['terbaik'] - k['awal']) / k['awal'] * 100:+.1f}%)".replace(".", ",")
        baris.append(f"{i}. <b>{nama}</b>{job_} - {fmt_durasi(k['detik'])}, {k['test']} test\n"
                     f"   ⚔️ {umum.fmt(k['awal'])} → {umum.fmt(k['terbaik'])}{naik}")

    baris.append("\n<b>Sesi kerja</b>:")
    for b in blok:
        afk_blok = f", AFK {fmt_durasi(b['afk'])}" if b["afk"] >= 60 else ""
        baris.append(f"• {b['mulai']:%H:%M} - {b['selesai']:%H:%M} ({fmt_durasi(b['kerja'])}, "
                     f"{len(b['acara'])} test{afk_blok})")
    keterangan = (f"\nℹ️ Dihitung dari mulai test pertama sampai hasil test terakhir. "
                  f"Jeda lebih dari {jeda_menit:g} menit antar test = istirahat.")
    if afk_menit > 0:
        keterangan += (f" Lebih dari {afk_menit:g} menit tidak menyentuh game (diam / buka aplikasi lain)"
                       " = AFK, dipotong.")
    baris.append(keterangan)
    return "\n".join(baris)
