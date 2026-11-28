"""OCR (baca tulisan dari gambar) + parser angka.

Urutan mesin OCR:
  1. OCR bawaan Windows (paket winocr) - tidak perlu install tambahan.
  2. Tesseract - cadangan, hanya dipakai kalau OCR Windows tidak bisa jalan
     atau kalau di config ditulis "mesin": "tesseract".

Cara baca: script mencari baris yang tulisannya mirip label (mis. "DMG Per Second"),
lalu mengambil angka di sebelah kanannya. Jadi posisi boleh bergeser sedikit.
"""
from __future__ import annotations

import difflib
import os
import re
import shutil
import threading
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

LABEL_TOTAL = "Total DMG"
LABEL_REKOR = "Highest Solo DMG Record"
VARIAN = ("asli", "kontras", "ambang")
TESSERACT_UMUM = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ---------------------------------------------------------------- modul boost (lazy + fallback aman)

_cv2_mod = None
_cv2_dicek = False
_rf_fuzz = None
_rf_dicek = False
_rapid_engine = None
_rapid_rusak: str | None = None
_rapid_lock = threading.Lock()


def _cv2():
    global _cv2_mod, _cv2_dicek
    if not _cv2_dicek:
        _cv2_dicek = True
        try:
            import cv2  # type: ignore
            _cv2_mod = cv2
        except Exception:
            _cv2_mod = None
    return _cv2_mod


def _rasio_mirip(a: str, b: str) -> float:
    """Skor kemiripan string 0.0–1.0: RapidFuzz (C++, 10-100x lebih cepat) -> fallback difflib."""
    global _rf_fuzz, _rf_dicek
    if not _rf_dicek:
        _rf_dicek = True
        try:
            from rapidfuzz import fuzz  # type: ignore
            _rf_fuzz = fuzz
        except Exception:
            _rf_fuzz = None
    if _rf_fuzz is not None:
        return _rf_fuzz.ratio(a, b) / 100.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def reset_cache_boost() -> None:
    """Reset cache deteksi modul boost setelah auto-install requirements selesai."""
    global _cv2_dicek, _rf_dicek, _rapid_rusak
    _cv2_dicek = False
    _rf_dicek = False
    _rapid_rusak = None


class OcrError(Exception):
    pass


@dataclass
class Kata:
    teks: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class HasilBaca:
    dps: int | None = None
    total: int | None = None
    rekor: int | None = None
    label_ketemu: bool = False
    teks: str = ""
    mesin: str = ""
    varian: str = ""
    kotak: tuple | None = None  # (x0, y0, x1, y1) letak baris hasil di dalam gambar
    panel: bool = False  # True = panel hasil asli (ada baris Total DMG / Highest Solo DMG Record di dekatnya)


# ---------------------------------------------------------------- parser angka

_PENGALI = {"": 1, "k": 1_000, "rb": 1_000, "m": 1_000_000, "jt": 1_000_000, "b": 1_000_000_000}
_POLA_ANGKA = re.compile(r"([\d.,]*\d[\d.,]*)(k|rb|m|jt|b)?")
_SALAH_BACA = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5"})


def parse_angka(teks: str) -> int | None:
    """Ubah tulisan jadi angka bulat.

    "52.140" -> 52140   "52,140" -> 52140   "52140" -> 52140
    "52.1K"  -> 52100   "1.2M"   -> 1200000 "1,234.5" -> 1235
    """
    if not teks:
        return None
    t = teks.strip().lower().replace(" ", "").strip(":;")
    m = _POLA_ANGKA.fullmatch(t)
    if not m:
        return None
    angka, akhiran = m.group(1).strip(".,"), m.group(2) or ""
    if not angka:
        return None
    bagian = re.split(r"[.,]", angka)
    pemisah = re.findall(r"[.,]", angka)
    if any(b == "" for b in bagian):
        return None
    if not pemisah:
        nilai = float(angka)
    else:
        ribuan_semua = 1 <= len(bagian[0]) <= 3 and all(len(b) == 3 for b in bagian[1:])
        if ribuan_semua and not akhiran:
            # 52.140 / 1,234,567 -> pemisah ribuan
            nilai = float("".join(bagian))
        elif ribuan_semua and akhiran and len(pemisah) > 1:
            nilai = float("".join(bagian))
        else:
            # pemisah terakhir = koma desimal, sisanya pemisah ribuan
            nilai = float("".join(bagian[:-1]) + "." + bagian[-1])
    return int(nilai * _PENGALI[akhiran] + 0.5)


def _perbaiki(teks: str) -> str:
    """Betulkan salah baca umum (O jadi 0, l jadi 1) HANYA kalau kata itu mayoritas angka."""
    t = teks.strip().strip(":;")
    digit = sum(c.isdigit() for c in t)
    if t and digit * 2 >= len(t):
        return t.translate(_SALAH_BACA)
    return t


def _mirip_angka(teks: str) -> bool:
    return _POLA_ANGKA.fullmatch(_perbaiki(teks).lower()) is not None


# ---------------------------------------------------------------- preprocessing

def siapkan_gambar(img: Image.Image, varian: str, perbesar: float = 2, ambang: int = 190) -> Image.Image:
    """Perbesar + (opsional) grayscale/threshold supaya tulisan lebih jelas.
    Memakai OpenCV (C++/SIMD) bila terpasang (5-15x lebih cepat), fallback ke Pillow."""
    w, h = img.size
    skala = max(1.0, float(perbesar))
    skala = min(skala, 4000 / max(w, h))  # jangan terlalu besar
    nw, nh = int(w * skala), int(h * skala)
    cv2 = _cv2()
    if cv2 is not None:
        arr = np.asarray(img.convert("RGB"))
        if skala > 1.01:
            interp = cv2.INTER_CUBIC if skala <= 2.5 else cv2.INTER_LINEAR
            arr = cv2.resize(arr, (nw, nh), interpolation=interp)
        if varian == "asli":
            return Image.fromarray(arr, mode="RGB")
        abu = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        lo, hi = int(abu.min()), int(abu.max())
        if hi > lo:
            abu = cv2.convertScaleAbs(abu, alpha=255.0 / (hi - lo), beta=-lo * 255.0 / (hi - lo))
        if varian == "kontras":
            return Image.fromarray(abu, mode="L")
        _, biner = cv2.threshold(abu, ambang - 1, 255, cv2.THRESH_BINARY_INV)
        return Image.fromarray(biner, mode="L")

    if skala > 1.01:
        img = img.resize((nw, nh), Image.LANCZOS)
    if varian == "asli":
        return img.convert("RGB")
    abu = ImageOps.autocontrast(ImageOps.grayscale(img))
    if varian == "kontras":
        return abu
    # "ambang": tulisan terang -> hitam, latar -> putih
    return abu.point(lambda p: 0 if p >= ambang else 255)


# ---------------------------------------------------------------- mesin OCR

_windows_rusak: str | None = None
_bahasa_dipakai: dict[str, str] = {}


def _bahasa_windows(minta: str) -> str:
    if minta in _bahasa_dipakai:
        return _bahasa_dipakai[minta]
    from winrt.windows.media.ocr import OcrEngine

    ada = [b.language_tag for b in OcrEngine.available_recognizer_languages]
    if not ada:
        raise OcrError("Windows belum punya paket bahasa untuk OCR.")
    pilih = ada[0]
    if minta in ada:
        pilih = minta
    else:
        for b in ada:
            if b.lower().startswith(minta[:2].lower()):
                pilih = b
                break
    _bahasa_dipakai[minta] = pilih
    return pilih


def _ocr_windows(img: Image.Image, bahasa: str) -> list[Kata]:
    import winocr

    hasil = winocr.recognize_pil_sync(img.convert("RGBA"), _bahasa_windows(bahasa))
    kata = []
    for baris in hasil["lines"]:
        for w in baris["words"]:
            k = w["bounding_rect"]
            kata.append(Kata(w["text"], k["x"], k["y"], k["width"], k["height"]))
    return kata


def cari_tesseract(path_config: str = "") -> str | None:
    for calon in (path_config, shutil.which("tesseract"), TESSERACT_UMUM):
        if calon and os.path.isfile(calon):
            return calon
    return None


def _ocr_tesseract(img: Image.Image, path_config: str) -> list[Kata]:
    exe = cari_tesseract(path_config)
    if not exe:
        raise OcrError("Tesseract belum terpasang (lihat README bagian Tesseract).")
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = exe
    d = pytesseract.image_to_data(img, config="--psm 11", output_type=pytesseract.Output.DICT)
    kata = []
    for i, t in enumerate(d["text"]):
        if t.strip():
            kata.append(Kata(t.strip(), d["left"][i], d["top"][i], d["width"][i], d["height"][i]))
    return kata


def _ocr_rapid(img: Image.Image) -> list[Kata]:
    """OCR memakai RapidOCR (PaddleOCR v4 via ONNX Runtime, lazy-loaded saat dibutuhkan)."""
    global _rapid_engine, _rapid_rusak
    if _rapid_rusak is not None:
        raise OcrError(_rapid_rusak)
    with _rapid_lock:
        if _rapid_engine is None:
            try:
                try:
                    from rapidocr_onnxruntime import RapidOCR  # type: ignore
                except ImportError:
                    from rapidocr import RapidOCR  # type: ignore
                _rapid_engine = RapidOCR()
            except Exception as e:
                _rapid_rusak = f"RapidOCR tidak tersedia: {e}"
                raise OcrError(_rapid_rusak) from e
    rgb = np.asarray(img.convert("RGB"))
    cv2 = _cv2()
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR) if cv2 is not None else rgb[..., ::-1].copy()
    keluaran = _rapid_engine(bgr)
    pasangan: list[tuple] = []
    if hasattr(keluaran, "boxes") and hasattr(keluaran, "txts"):
        boxes = keluaran.boxes if keluaran.boxes is not None else []
        txts = keluaran.txts if keluaran.txts is not None else []
        for b, t in zip(boxes, txts):
            pasangan.append((b, str(t)))
    else:
        hasil = keluaran[0] if isinstance(keluaran, tuple) else keluaran
        for item in (hasil or []):
            if not item or len(item) < 2:
                continue
            # Format standar rapidocr_onnxruntime: [box, text, score]; cadangan: [text, score, box]
            if isinstance(item[0], str) and len(item) >= 3:
                pasangan.append((item[2], item[0]))
            else:
                pasangan.append((item[0], str(item[1])))
    kata: list[Kata] = []
    for box, teks in pasangan:
        teks = teks.strip()
        if not teks:
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        w_box, h_box = max(1.0, x1 - x0), max(1.0, y1 - y0)
        # RapidOCR mengembalikan per baris; pecah jadi per kata secara proporsional
        # agar parser label+angka (_semua_label, bacabuild, _cari_nick) bekerja identik dengan WinOCR.
        bagian = teks.split()
        if len(bagian) == 1:
            kata.append(Kata(bagian[0], x0, y0, w_box, h_box))
        else:
            total_len = max(1, len(teks))
            pos = 0
            for b in bagian:
                idx = teks.find(b, pos)
                if idx < 0:
                    idx = pos
                wx = x0 + (idx / total_len) * w_box
                ww = max(1.0, (len(b) / total_len) * w_box)
                kata.append(Kata(b, wx, y0, ww, h_box))
                pos = idx + len(b)
    return kata


def _jalankan_mesin(img: Image.Image, cfg_ocr: dict, prioritas: str = "cepat") -> tuple[list[Kata], str]:
    """Jalankan mesin OCR terbaik.
    prioritas='cepat'  : WinOCR dulu (ringan saat standby) -> RapidOCR -> Tesseract.
    prioritas='akurat' : RapidOCR dulu (paling akurat untuk font game/Detailed Stats) -> WinOCR -> Tesseract."""
    global _windows_rusak
    mesin = str(cfg_ocr.get("mesin", "auto")).lower()
    if mesin == "rapid":
        return _ocr_rapid(img), "rapidocr"
    if mesin == "auto" and prioritas == "akurat" and _rapid_rusak is None:
        try:
            return _ocr_rapid(img), "rapidocr"
        except Exception:
            pass
    if mesin in ("auto", "windows") and _windows_rusak is None:
        try:
            return _ocr_windows(img, cfg_ocr.get("bahasa", "en-US")), "windows"
        except Exception as e:  # winocr tidak ada / bahasa tidak ada / dll
            if mesin == "windows":
                raise OcrError(f"OCR Windows gagal: {e}") from e
            _windows_rusak = str(e)
    if mesin == "windows":
        raise OcrError(f"OCR Windows gagal: {_windows_rusak}")
    if mesin == "auto" and _rapid_rusak is None:
        try:
            return _ocr_rapid(img), "rapidocr"
        except Exception:
            pass
    try:
        return _ocr_tesseract(img, cfg_ocr.get("tesseract_path", "")), "tesseract"
    except OcrError as e:
        if _windows_rusak:
            raise OcrError(f"OCR Windows gagal ({_windows_rusak}) dan cadangan juga gagal: {e}") from e
        raise


# ---------------------------------------------------------------- tafsir hasil

def _kelompokkan_baris(kata: list[Kata]) -> list[list[Kata]]:
    """Kumpulkan kata yang tingginya sejajar jadi satu baris, urut kiri ke kanan."""
    baris: list[list[Kata]] = []
    for k in sorted(kata, key=lambda k: k.y + k.h / 2):
        cy = k.y + k.h / 2
        for b in baris:
            rata_cy = sum(x.y + x.h / 2 for x in b) / len(b)
            rata_h = sum(x.h for x in b) / len(b)
            if abs(cy - rata_cy) <= 0.6 * max(k.h, rata_h):
                b.append(k)
                break
        else:
            baris.append([k])
    for b in baris:
        b.sort(key=lambda k: k.x)
    return baris


def _norm(teks: str) -> str:
    return re.sub(r"[^a-z0-9]", "", teks.lower())


def _semua_label(baris: list[list[Kata]], label: str) -> list[tuple[int | None, float, list[Kata], bool]]:
    """Semua tempat tulisan yang mirip `label`: daftar (angka, skor, kata label+angka, angka disingkat?).

    "Disingkat" = angkanya pakai K/M/B (mis. "4.9M"). Itu ciri meteran DPS saat bertarung;
    layar hasil VICTORY selalu menulis angka lengkap (mis. "4900000").

    Satu "baris" bisa ikut berisi tulisan lain yang kebetulan sejajar (jendela lain, monitor
    sebelah), jadi yang dicari adalah potongan kata yang mirip label, lalu angka TEPAT di
    kanannya.
    """
    target = _norm(label)
    jumlah_kata = max(1, len(label.split()))
    calon = []
    for b in baris:
        terbaik = None
        for s in range(len(b)):
            if _mirip_angka(b[s].teks):
                continue
            for e in range(s + 1, min(len(b), s + jumlah_kata + 2) + 1):
                if _mirip_angka(b[e - 1].teks):
                    break
                teks = _norm("".join(k.teks for k in b[s:e]))
                if not teks:
                    continue
                skor = 1.0 if target in teks and len(teks) <= len(target) + 12 else \
                    _rasio_mirip(target, teks)
                if skor < 0.85:  # 0.75 terlalu longgar: "DMG Record" sempat dikira "DMG Per Second"
                    continue
                # Angka: kata-kata angka yang menyambung tepat setelah label.
                # Potongan angka (mis. "52" "140") hanya disambung kalau jaraknya rapat.
                j = e
                while j < len(b) and _mirip_angka(b[j].teks) and (
                        j == e or b[j].x - (b[j - 1].x + b[j - 1].w) <= 0.8 * b[j - 1].h):
                    j += 1
                angka_kata = b[e:j]
                jarak_ok = bool(angka_kata) and angka_kata[0].x - (b[e - 1].x + b[e - 1].w) <= 30 * b[e - 1].h
                teks_angka = "".join(_perbaiki(k.teks) for k in angka_kata)
                angka = parse_angka(teks_angka) if jarak_ok else None
                singkat = angka is not None and any(c.isalpha() for c in teks_angka)
                nilai = (angka is not None, skor)
                if terbaik is None or nilai > terbaik[0]:
                    terbaik = (nilai, angka, skor, b[s:e] + (angka_kata if jarak_ok else []), singkat)
        if terbaik:
            calon.append(terbaik[1:])
    return calon


def _cari_label(baris: list[list[Kata]], label: str):
    """Cari tulisan yang mirip `label`.

    Mengembalikan (angka di kanannya, label ketemu?, kata-kata label+angka).
    Yang punya angka diutamakan (penting saat membaca satu layar penuh,
    karena tulisan yang sama bisa muncul di jendela lain tanpa angka).
    """
    calon = _semua_label(baris, label)
    if not calon:
        return None, False, [], False
    angka, _, kata, singkat = max(calon, key=lambda c: (c[0] is not None, c[1]))
    return angka, True, kata, singkat


def tafsir(kata: list[Kata], label: str) -> HasilBaca:
    baris = _kelompokkan_baris(kata)
    hasil = HasilBaca(teks="\n".join(" ".join(k.teks for k in b) for b in baris))
    if not label.strip():
        # Mode "angka saja": area cuma berisi angka, tanpa label.
        calon = [parse_angka(_perbaiki(k.teks)) for k in kata if _mirip_angka(k.teks)]
        calon = [c for c in calon if c is not None]
        if calon:
            hasil.dps = max(calon)
            hasil.label_ketemu = True
        return hasil
    # Tulisan "DMG Per Second" bisa muncul lebih dari sekali di layar: panel hasil VICTORY,
    # dan juga meteran DPS saat bertarung ("DMG Per Second 4.9M" + "Total DMG 93.8M").
    # Ciri panel hasil asli:
    #   - angkanya ditulis lengkap (meteran pakai singkatan K/M), dan
    #   - ada baris "Highest Solo DMG Record", atau baris "Total DMG" berangka lengkap, di dekatnya.
    pilihan = None
    for angka, skor, b_dps, dps_singkat in _semua_label(baris, label):
        tinggi = max(k.h for k in b_dps)
        tengah = sum(k.y + k.h / 2 for k in b_dps) / len(b_dps)
        kiri, kanan = min(k.x for k in b_dps), max(k.x + k.w for k in b_dps)

        def satu_panel(b):
            cy = sum(k.y + k.h / 2 for k in b) / len(b)
            bx0, bx1 = min(k.x for k in b), max(k.x + k.w for k in b)
            return abs(cy - tengah) <= 6 * tinggi and bx0 < kanan and bx1 > kiri

        dekat = [b for b in baris if b is not b_dps and satu_panel(b)]
        total, _, b_total, total_singkat = _cari_label(dekat, LABEL_TOTAL)
        rekor, ada_rekor, b_rekor, _ = _cari_label(dekat, LABEL_REKOR)
        panel = not dps_singkat and (ada_rekor or (total is not None and not total_singkat))
        nilai = (angka is not None, panel, skor)
        if pilihan is None or nilai > pilihan[0]:
            pilihan = (nilai, angka, total, rekor, panel, list(b_dps) + b_total + b_rekor)
    if pilihan is None:
        return hasil
    _, hasil.dps, hasil.total, hasil.rekor, hasil.panel, terpakai = pilihan
    hasil.label_ketemu = True
    hasil.kotak = (min(k.x for k in terpakai), min(k.y for k in terpakai),
                   max(k.x + k.w for k in terpakai), max(k.y + k.h for k in terpakai))
    return hasil


def baca_hasil(img: Image.Image, label: str, cfg_ocr: dict, varian_dicoba=VARIAN,
               prioritas: str = "cepat") -> HasilBaca:
    """Fungsi utama: gambar -> HasilBaca. Mencoba beberapa cara preprocessing."""
    terbaik = HasilBaca()
    for varian in varian_dicoba:
        siap = siapkan_gambar(img, varian, cfg_ocr.get("perbesar", 2), cfg_ocr.get("ambang", 190))
        prio = prioritas if varian == "asli" else "akurat"
        kata, mesin = _jalankan_mesin(siap, cfg_ocr, prioritas=prio)
        hasil = tafsir(kata, label)
        hasil.mesin, hasil.varian = mesin, varian
        if hasil.kotak:
            skala = siap.width / img.width  # kembalikan ke ukuran gambar asli
            hasil.kotak = tuple(int(v / skala) for v in hasil.kotak)
        if _yakin(hasil):
            return hasil
        if _lebih_baik(hasil, terbaik):
            terbaik = hasil
    return terbaik


# Damage Challenge berlangsung sekitar 2 menit, jadi Total DMG / DPS selalu sekitar 116-120.
# Dari 270+ screenshot asli: semuanya di 110-120. Kalau jauh dari itu, ada angka yang salah baca
# (mis. tertutup efek di layar), dan cara baca lain dicoba dulu.
DETIK_MIN, DETIK_MAX = 95, 135


def konsisten(h: HasilBaca) -> bool:
    if not h.dps or not h.total:
        return True
    return DETIK_MIN <= h.total / h.dps <= DETIK_MAX


def _yakin(h: HasilBaca) -> bool:
    return h.dps is not None and h.panel and konsisten(h)


def _nilai(h: HasilBaca) -> tuple:
    return (h.dps is not None, h.panel, konsisten(h), h.label_ketemu)


def _lebih_baik(a: HasilBaca, b: HasilBaca) -> bool:
    return not b.mesin or _nilai(a) > _nilai(b)


def cari_di_layar(img: Image.Image, label: str, cfg_ocr: dict) -> HasilBaca:
    """Mode OTOMATIS: cari panel hasil di screenshot satu layar penuh (tanpa setup area).

    Dibaca ukuran asli dulu (~0,1 detik, di 23 dari 23 foto asli sudah cukup). Diperbesar 2x
    HANYA kalau ada tanda-tanda panel hasil (kata DMG/Second/Total), supaya saat layar hasil
    tidak tampil bot tidak buang waktu & CPU.
    """
    terbaik = HasilBaca()
    for besar in (1, 2):
        prio = "cepat" if besar == 1 else "akurat"
        hasil = baca_hasil(img, label, dict(cfg_ocr, perbesar=besar), ("asli",), prioritas=prio)
        if _yakin(hasil):
            return hasil
        if _lebih_baik(hasil, terbaik):
            terbaik = hasil
        if besar == 1:
            tidak_ada = not hasil.label_ketemu and not re.search(r"dmg|second|total", hasil.teks, re.I)
            meteran = hasil.label_ketemu and not hasil.panel and hasil.dps is not None  # HUD saat bertarung
            if tidak_ada or meteran:
                break
    if terbaik.panel and terbaik.kotak:
        # Panel ketemu tapi angkanya meragukan: baca ulang bagian panel saja dengan cara paling akurat.
        x0, y0, x1, y1 = terbaik.kotak
        kiri, atas = max(0, x0 - 50), max(0, y0 - 35)
        potong = img.crop((kiri, atas, min(img.width, x1 + 50), min(img.height, y1 + 35)))
        hasil = baca_hasil(potong, label, dict(cfg_ocr, perbesar=3), VARIAN, prioritas="akurat")
        if _lebih_baik(hasil, terbaik):
            hasil.kotak = terbaik.kotak
            terbaik = hasil
    return terbaik
