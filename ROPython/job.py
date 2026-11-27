"""Deteksi JOB karakter dari ikon kecil di samping tulisan "Lv" (kiri atas layar game).

HANYA melihat screenshot. Cara kerja:
1. Cari tulisan "Lv 93" di kiri atas jendela game (OCR).
2. Ikon job = lingkaran kecil berwarna tepat di kiri tulisan itu.
3. Cocokkan dengan:
   a. ikon asli dari game yang pernah "diajarkan" (lewat /job), paling dipercaya;
   b. kalau belum ada, 15 logo job di folder job_ikon (warna + bentuk gambar tengah).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

import ocr
import umum

FOLDER_LOGO = umum.FOLDER / "job_ikon"
FOLDER_BELAJAR = umum.FOLDER_DATA / "job_belajar"
UKURAN = 24  # semua ikon dibandingkan dalam ukuran 24x24


@dataclass
class HasilJob:
    job: str | None = None
    yakin: bool = False
    skor: float = 0.0
    ikon: Image.Image | None = None  # potongan ikon dari layar (untuk diajarkan)


# ---------------------------------------------------------------- bantuan gambar

def _arr(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB").resize((UKURAN, UKURAN), Image.LANCZOS)).astype(np.float32)


def _lingkaran(r_dalam: float, r_luar: float) -> np.ndarray:
    yy, xx = np.mgrid[0:UKURAN, 0:UKURAN]
    c = (UKURAN - 1) / 2
    d = np.hypot(xx - c, yy - c) / (UKURAN / 2)
    return (d >= r_dalam) & (d <= r_luar)


_CINCIN = _lingkaran(0.55, 0.85)  # bagian warna (bukan gambar tengah)
_TENGAH = _lingkaran(0.0, 0.55)


def _warna(a: np.ndarray, area: np.ndarray) -> tuple[float, float, float]:
    """(hue derajat, saturasi, kecerahan) dari bagian yang paling berwarna."""
    px = a[area] / 255.0
    mx, mn = px.max(1), px.min(1)
    sel = (mx - mn) >= np.percentile(mx - mn, 60)
    p, mx, mn = px[sel], mx[sel], mn[sel]
    d = np.where(mx - mn == 0, 1e-6, mx - mn)
    r, g, b = p[:, 0], p[:, 1], p[:, 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    ang = np.radians(h)
    hue = (np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) + 360) % 360
    sat = float(np.median((mx - mn) / np.where(mx == 0, 1, mx)))
    return float(hue), sat, float(np.median(mx))


def _jarak_warna(a, b) -> float:
    dh = abs(a[0] - b[0]) % 360
    dh = min(dh, 360 - dh)
    return (dh / 8) ** 2 + ((a[1] - b[1]) / 0.3) ** 2 + ((a[2] - b[2]) / 0.25) ** 2


def _bentuk(a: np.ndarray) -> np.ndarray:
    """Gambar tengah (putih) sebagai pola terang-gelap yang dinormalisasi."""
    abu = a.mean(2) - (a.max(2) - a.min(2)) * 0.5  # putih = terang & tidak berwarna
    v = abu[_TENGAH]
    v = v - v.mean()
    n = np.linalg.norm(v)
    return v / n if n else v


def _korelasi(a: np.ndarray, b: np.ndarray) -> float:
    x = (a - a.mean()).ravel()
    y = (b - b.mean()).ravel()
    n = np.linalg.norm(x) * np.linalg.norm(y)
    return float(x @ y / n) if n else 0.0


# ---------------------------------------------------------------- data acuan

_logo: dict[str, np.ndarray] | None = None


def _muat_logo() -> dict[str, np.ndarray]:
    global _logo
    if _logo is None:
        _logo = {}
        for f in sorted(FOLDER_LOGO.glob("*.png")):
            img = Image.open(f).convert("RGB")
            w, h = img.size
            # logo bintang: ambil bagian dalam saja supaya mirip ikon bulat di game
            k = 0.16
            img = img.crop((int(w * k), int(h * k), int(w * (1 - k)), int(h * (1 - k))))
            _logo[f.stem] = _arr(img)
    return _logo


def _muat_belajar() -> list[tuple[str, np.ndarray]]:
    hasil = []
    if FOLDER_BELAJAR.exists():
        for f in sorted(FOLDER_BELAJAR.glob("*/*.png")):
            hasil.append((f.parent.name, _arr(Image.open(f))))
    return hasil


def ajarkan(nama_job: str, ikon: Image.Image) -> Path:
    """Simpan ikon asli dari game sebagai contoh job ini."""
    folder = FOLDER_BELAJAR / nama_job
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{len(list(folder.glob('*.png'))) + 1}.png"
    ikon.convert("RGB").resize((UKURAN, UKURAN), Image.LANCZOS).save(f)
    return f


def daftar_job() -> list[str]:
    return list(_muat_logo().keys())


def nama_resmi(teks: str) -> str | None:
    for j in daftar_job():
        if j.lower() == teks.strip().lower():
            return j
    return None


# ---------------------------------------------------------------- cari & kenali

def potong_ikon(img: Image.Image, cfg_ocr: dict) -> Image.Image | None:
    """Cari tulisan "Lv" di kiri atas gambar jendela game, lalu potong ikon job di kirinya."""
    W, H = img.size
    daerah = img.crop((0, 0, int(W * 0.35), int(H * 0.2)))
    lv, skala = [], 2
    # Layar game kadang redup (ada popup / diam lama): coba juga versi yang dicerahkan.
    for skala, varian in ((2, "asli"), (3, "kontras"), (2, "kontras")):
        g = ocr.siapkan_gambar(daerah, varian, skala)
        try:
            kata, _ = ocr._jalankan_mesin(g, cfg_ocr)
        except ocr.OcrError:
            return None
        lv = [k for k in kata if re.fullmatch(r"[Ll]v\.?\d*", k.teks)]
        if lv:
            break
    if not lv:
        # Tulisan "Lv" tidak terbaca (layar sangat redup): cari lingkarannya langsung di pojok kiri atas.
        h = H * 0.0156  # tinggi tulisan "Lv" kira-kira 1,56% tinggi jendela
        return _cari_lingkaran(img, 0, 0, h, kotak=(0, 0, int(W * 0.09), int(H * 0.09)), v_min=0.04)
    k = min(lv, key=lambda k: k.y)
    x, y, h = k.x / skala, k.y / skala, k.h / skala
    return _cari_lingkaran(img, x, y, h)


def _cari_lingkaran(img: Image.Image, x: float, y: float, h: float,
                    kotak: tuple | None = None, v_min: float = 0.15) -> Image.Image | None:
    """Ikon job = lingkaran kecil berwarna rata di kiri tulisan "Lv".
    Coba banyak posisi/ukuran di sekitar situ, pilih yang paling mirip "lingkaran satu warna"."""
    if kotak:
        x0, y0, x1, y1 = kotak
    else:
        x0, y0 = int(max(0, x - 3.2 * h)), int(max(0, y - 1.5 * h))
        x1, y1 = int(x), int(y + 2.0 * h)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    a = np.asarray(img.crop((x0, y0, x1, y1)).convert("HSV")).astype(np.float32)
    H, S, V = a[..., 0] * (360 / 255), a[..., 1] / 255, a[..., 2] / 255
    rad = np.radians(H)
    terbaik = (-9.0, None)
    for d in np.arange(1.3 * h, 2.3 * h, 0.15 * h):
        r = d / 2
        yy, xx = np.mgrid[-int(r * 1.3):int(r * 1.3) + 1, -int(r * 1.3):int(r * 1.3) + 1]
        jarak = np.hypot(xx, yy) / r
        cincin = (jarak >= 0.55) & (jarak <= 0.9)
        luar = (jarak >= 1.05) & (jarak <= 1.3)
        m = int(r * 1.3)
        for cy in range(m, a.shape[0] - m):
            for cx in range(m, a.shape[1] - m):
                sl = (slice(cy - m, cy + m + 1), slice(cx - m, cx + m + 1))
                s_c, v_c = S[sl][cincin], V[sl][cincin]
                berwarna = (s_c > 0.3) & (v_c > v_min)
                frac = berwarna.mean()
                if frac < 0.5:
                    continue
                hc = rad[sl][cincin][berwarna]
                rata = np.hypot(np.cos(hc).mean(), np.sin(hc).mean())  # 1 = warnanya seragam
                s_l = S[sl][luar]
                beda_luar = np.abs(np.median(s_c) - np.median(s_l))
                skor = frac + rata + 0.5 * beda_luar
                if skor > terbaik[0]:
                    terbaik = (skor, (x0 + cx - r, y0 + cy - r, x0 + cx + r, y0 + cy + r))
    if terbaik[1] is None or terbaik[0] < 1.4:
        return None
    return img.crop(tuple(int(round(v)) for v in terbaik[1]))


def kenali(ikon: Image.Image) -> HasilJob:
    a = _arr(ikon)
    # 1) ikon asli yang pernah diajarkan (geser sedikit supaya tahan posisi meleset 1-2 piksel)
    terbaik = (None, -1.0)
    for nama, t in _muat_belajar():
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                s = _korelasi(np.roll(a, (dy, dx), (0, 1)), t)
                if s > terbaik[1]:
                    terbaik = (nama, s)
    if terbaik[0] and terbaik[1] >= 0.85:
        return HasilJob(terbaik[0], True, terbaik[1], ikon)

    # 2) logo acuan: warna cincin dulu, lalu bentuk gambar tengah
    w_ikon, b_ikon = _warna(a, _CINCIN), _bentuk(a)
    jarak = []
    for nama, t in _muat_logo().items():
        j_warna = _jarak_warna(w_ikon, _warna(t, _CINCIN))
        j_bentuk = 1 - float(b_ikon @ _bentuk(t))
        jarak.append((j_warna + 0.5 * j_bentuk, nama))
    jarak.sort()
    if not jarak:
        return HasilJob(ikon=ikon)
    j1, nama = jarak[0]
    beda = jarak[1][0] - j1 if len(jarak) > 1 else 9.0
    yakin = j1 < 1.5 and beda >= 0.4
    return HasilJob(nama, yakin, round(j1, 2), ikon)


def baca_info_karakter(img: Image.Image, cfg_ocr: dict) -> tuple[str, str] | None:
    """Halaman info karakter: nick ada tepat di atas baris "ID:60542798".

    Mengembalikan (nick, id) atau None kalau halaman itu tidak terlihat jelas.
    """
    for skala, varian in ((1, "asli"), (2, "asli"), (1.5, "kontras"), (2, "kontras")):
        g = ocr.siapkan_gambar(img, varian, skala)
        kata, _ = ocr._jalankan_mesin(g, cfg_ocr)
        hasil = _cari_nick(kata)
        if hasil:
            return hasil
    return None


def _cari_nick(kata: list) -> tuple[str, str] | None:
    for k in kata:
        m = re.fullmatch(r"ID\s*[:;]?\s*(\d{6,})?", k.teks)
        if not m:
            continue
        nomor = m.group(1)
        if not nomor:  # "ID:" dan angkanya terpisah
            kanan = [x for x in kata if abs(x.y - k.y) < k.h * 0.6 and 0 <= x.x - (k.x + k.w) < k.h * 1.5]
            if not kanan or not re.fullmatch(r"\d{6,}", kanan[0].teks):
                continue
            nomor = kanan[0].teks
        h = k.h
        # Kata-kata di baris tepat di atas ID, mulai di sekitar posisi kiri ID.
        atas = [x for x in kata
                if 0.6 * h < k.y - x.y < 3.2 * h and k.x - 1.5 * h <= x.x <= k.x + 6 * h]
        if not atas:
            continue
        y_baris = max(x.y for x in atas)  # baris yang paling dekat dengan ID
        baris = sorted((x for x in atas if abs(x.y - y_baris) < 0.6 * h), key=lambda x: x.x)
        nick = baris[0].teks
        for a, b in zip(baris, baris[1:]):
            if b.x - (a.x + a.w) > 1.2 * h:
                break
            nick += " " + b.teks
        nick = nick.strip()
        if 2 <= len(nick) <= 24:
            return nick, nomor
    return None


def baca_nama_tengah(img: Image.Image, cfg_ocr: dict) -> list[str]:
    """Semua tulisan hijau di sekitar tengah jendela game, urut dari huruf PALING BESAR.

    Nama karakter kita = hijau, di bawah badannya, hurufnya lebih besar dari nama pet
    ("Soloish97" tinggi 18 px vs pet "Dusk" 11 px). Jadi hasil[0] = calon nama karakter.
    Angka murni (heal) dan tulisan < 3 huruf dibuang."""
    w, h = img.size
    potong = img.convert("RGB").crop((int(w * 0.25), int(h * 0.30), int(w * 0.75), int(h * 0.85)))
    a = np.asarray(potong).astype(int)
    r, g_, b = a[..., 0], a[..., 1], a[..., 2]
    hijau = (g_ > 170) & (g_ - b > 70) & (r > 120) & (g_ >= r - 10)
    saring = Image.fromarray(np.where(hijau, 0, 255).astype("uint8")).convert("RGB")
    for skala in (1, 2):
        g = saring if skala == 1 else saring.resize((saring.width * 2, saring.height * 2))
        kata, _ = ocr._jalankan_mesin(g, cfg_ocr)
        calon = []
        for bar in ocr._kelompokkan_baris(kata):
            teks = "".join(k.teks for k in bar).strip()
            n = ocr._norm(teks)
            if 3 <= len(teks) <= 24 and len(n) >= 3 and not n.isdigit() and re.search(r"[A-Za-z]", teks):
                calon.append((max(k.h for k in bar), teks))
        if calon:
            calon.sort(key=lambda c: -c[0])
            return [t for _, t in calon]
    return []


def nama_di_tengah(img: Image.Image, cfg_ocr: dict, nicks: dict[str, str]) -> set[str]:
    """Baca papan nama di sekitar tengah jendela game (nama karakter kita tampil di bawah
    badannya, dan karakter kita selalu di tengah layar). Hasil: kunci `nicks` yang terlihat.

    `nicks` = {pid: nick}. Hanya nick yang sudah dikenal yang bisa dicocokkan."""
    import difflib

    calon = {pid: ocr._norm(n) for pid, n in nicks.items() if n and len(ocr._norm(n)) >= 3}
    if not calon:
        return set()
    w, h = img.size
    potong = img.convert("RGB").crop((int(w * 0.25), int(h * 0.30), int(w * 0.75), int(h * 0.85)))
    # Nama karakter kita berwarna hijau-kuning. Ambil hanya warna itu (jadi hitam di atas putih),
    # supaya lantai / efek di belakangnya tidak mengganggu.
    a = np.asarray(potong).astype(int)
    r, g_, b = a[..., 0], a[..., 1], a[..., 2]
    hijau = (g_ > 170) & (g_ - b > 70) & (r > 120) & (g_ >= r - 10)
    saring = Image.fromarray(np.where(hijau, 0, 255).astype("uint8")).convert("RGB")
    terlihat: set[str] = set()
    for skala in (1, 2):
        g = saring if skala == 1 else saring.resize((saring.width * 2, saring.height * 2))
        kata, _ = ocr._jalankan_mesin(g, cfg_ocr)
        teks_baris = []
        for b in ocr._kelompokkan_baris(kata):
            teks_baris.append(ocr._norm("".join(k.teks for k in b)))
            teks_baris += [ocr._norm(k.teks) for k in b]
        for pid, n in calon.items():
            for t in teks_baris:
                if t and (t == n or (len(n) >= 5 and difflib.SequenceMatcher(None, n, t).ratio() >= 0.88)):
                    terlihat.add(pid)
                    break
        if terlihat:
            break
    return terlihat


def deteksi(img: Image.Image, cfg_ocr: dict) -> HasilJob:
    ikon = potong_ikon(img, cfg_ocr)
    if ikon is None:
        return HasilJob()
    return kenali(ikon)
