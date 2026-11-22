"""Perkiraan DPS puncak dari test PERTAMA karakter baru (info saja, target tidak diubah).

Pola diambil dari karakter-karakter sebelumnya (riwayat.csv): puncak / test pertama.
Karakter yang awalnya sudah kuat naiknya sedikit, yang masih lemah naiknya banyak, jadi dibagi 2 kelompok.
Diuji ke data 22/11 (19 karakter): meleset median 13%, peringatan "target berat" tepat 10 dari 12.
"""
from __future__ import annotations

import catatan
import umum

BATAS_KELOMPOK = 2_500_000   # DPS awal di bawah ini = kelompok "masih lemah"
MIN_TES = 5                  # karakter dipakai sebagai contoh kalau sudah dites minimal segini
MIN_CONTOH = 4               # kurang dari ini -> pakai pola bawaan
PENCILAN = 3.0               # naik >3x = test pertama tidak wajar (belum pakai equip / salah baca), dibuang
BAWAAN = {0: (1.34, 1.74), 1: (1.05, 1.17)}  # hasil analisa 22/11, dipakai kalau contoh belum cukup


def _kelompok(dps: int) -> int:
    return 0 if dps < BATAS_KELOMPOK else 1


def _kuantil(xs: list[float], f: float) -> float:
    xs = sorted(xs)
    i = (len(xs) - 1) * f
    lo = int(i)
    return xs[lo] + (xs[min(lo + 1, len(xs) - 1)] - xs[lo]) * (i - lo)


def pola(pids, kecuali: str = "") -> dict[int, list[float]]:
    """Rasio puncak/pertama per kelompok dari semua karakter yang sudah cukup dites."""
    hasil: dict[int, list[float]] = {0: [], 1: []}
    for pid in pids:
        if pid == kecuali:
            continue
        try:
            d = [x["dps"] for x in catatan.baca_ok(pid) if x.get("dps")]
        except Exception:
            continue
        if len(d) < MIN_TES or d[0] <= 0:
            continue
        r = max(d) / d[0]
        if r < PENCILAN:
            hasil[_kelompok(d[0])].append(r)
    return hasil


def rentang(dps_awal: int, pids, kecuali: str = "") -> tuple[int, int, int]:
    """(perkiraan bawah, perkiraan atas, jumlah contoh yang dipakai; 0 = pola bawaan)."""
    g = _kelompok(dps_awal)
    r = pola(pids, kecuali)[g]
    if len(r) >= MIN_CONTOH:
        lo, hi, n = _kuantil(r, 0.2), _kuantil(r, 0.8), len(r)
    else:
        (lo, hi), n = BAWAAN[g], 0
    lo = max(lo, 1.0)
    bulat = lambda x: int(round(x, -4))  # perkiraan, tidak perlu sampai satuan
    return bulat(dps_awal * lo), bulat(dps_awal * max(hi, lo)), n


def teks(dps_awal: int, target: int, pids, kecuali: str = "") -> str:
    lo, hi, _ = rentang(dps_awal, pids, kecuali)
    dasar = f"📈 Perkiraan puncak: <b>{umum.fmt(lo)} – {umum.fmt(hi)}</b>"
    if not target or dps_awal >= target:
        return dasar
    if hi < target:
        return (f"{dasar}\n⚠️ Target {umum.fmt(target)} kemungkinan <b>berat</b> untuk karakter ini. "
                "Pertimbangkan bicara dengan pembeli lebih awal.")
    if lo >= target:
        return f"{dasar} → target hampir pasti tembus"
    return f"{dasar} → target bisa tembus"

