"""MODE TES - cek akurasi bacaan sebelum bot dipakai serius.

Cara pakai (atau klik 3_tes_ocr.bat):
  python tes_ocr.py              -> screenshot area profil aktif sekali, lalu baca
  python tes_ocr.py gambar.png   -> baca dari file gambar
  python tes_ocr.py --contoh     -> baca semua gambar di folder "contoh"
  python tes_ocr.py --uji        -> uji parser angka
  python tes_ocr.py --regresi    -> uji SEMUA screenshot di contoh/screenshot terhadap kunci_jawaban.json
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

import layar
import ocr
import umum


def tampilkan(nama: str, img: Image.Image, label: str, cfg_ocr: dict) -> ocr.HasilBaca:
    hasil = ocr.baca_hasil(img, label, cfg_ocr)
    print(f"\n=== {nama} ({img.width}x{img.height}) ===")
    print(f"Mesin OCR      : {hasil.mesin} (cara: {hasil.varian})")
    print(f"Label ketemu   : {'YA' if hasil.label_ketemu else 'TIDAK'}  (label: \"{label}\")")
    print(f"DPS            : {umum.fmt(hasil.dps)}")
    print(f"Total DMG      : {umum.fmt(hasil.total)}")
    print(f"Rekor tertinggi: {umum.fmt(hasil.rekor)}")
    print("Semua tulisan yang terbaca:")
    for baris in hasil.teks.splitlines():
        print(f"   | {baris}")
    return hasil


def uji_parser() -> bool:
    kasus = {
        "52.140": 52140, "52,140": 52140, "52140": 52140, "52.1K": 52100, "1.2M": 1200000,
        "2717924": 2717924, "1,234,567": 1234567, "1.234.567": 1234567, "3,5jt": 3500000,
        "1,234.5": 1235, "750k": 750000, "2.5B": 2500000000, "abc": None, "": None,
    }
    lolos = True
    for teks, harap in kasus.items():
        dapat = ocr.parse_angka(teks)
        ok = dapat == harap
        lolos &= ok
        print(f"  {'OK   ' if ok else 'SALAH'} {teks!r:>12} -> {dapat}" + ("" if ok else f" (harusnya {harap})"))
    print("Parser angka:", "SEMUA BENAR" if lolos else "ADA YANG SALAH")
    return lolos


def uji_regresi(label: str, cfg_ocr: dict) -> bool:
    """Baca semua screenshot asli di contoh/screenshot, bandingkan dengan kunci_jawaban.json."""
    import json

    folder = umum.FOLDER / "contoh" / "screenshot"
    kunci_file = folder / "kunci_jawaban.json"
    if not kunci_file.exists():
        print(f"Tidak ada {kunci_file}")
        return False
    kunci = json.loads(kunci_file.read_text(encoding="utf-8"))
    salah = 0
    for i, (nama, harap) in enumerate(kunci.items(), 1):
        img = Image.open(folder / nama).convert("RGB")
        h = ocr.cari_di_layar(img, label, cfg_ocr)
        dapat = h.dps if (h.dps is not None and h.panel) else None
        if dapat != harap["dps"]:
            salah += 1
            print(f"  SALAH {nama}: dapat {umum.fmt(dapat)}, harusnya {umum.fmt(harap['dps'])}")
        if i % 50 == 0:
            print(f"  ... {i}/{len(kunci)}")
    print(f"Regresi: {len(kunci) - salah}/{len(kunci)} benar")
    return salah == 0


def main() -> int:
    umum.siapkan_konsol()
    umum.aktifkan_dpi_aware()
    arg = sys.argv[1:]
    if "--uji" in arg:
        return 0 if uji_parser() else 1
    if "--regresi" in arg:
        cfg = umum.muat_config()
        return 0 if uji_regresi("DMG Per Second", cfg["ocr"]) else 1
    try:
        cfg = umum.muat_config()
    except umum.ConfigError as e:
        print("MASALAH CONFIG:", e)
        return 2
    profil = cfg["profil"][cfg["profil_aktif"]]
    label = profil.get("label", "DMG Per Second")
    try:
        if "--contoh" in arg:
            daftar = sorted((umum.FOLDER / "contoh").glob("*.png"))
            if not daftar:
                print("Folder 'contoh' kosong.")
                return 1
            for f in daftar:
                tampilkan(f.name, Image.open(f).convert("RGB"), label, cfg["ocr"])
            return 0
        if arg:
            f = Path(arg[0])
            if not f.exists():
                print(f"File tidak ditemukan: {f}")
                return 1
            tampilkan(f.name, Image.open(f).convert("RGB"), label, cfg["ocr"])
            return 0
        if not umum.area_valid(profil.get("area")):
            # Mode OTOMATIS: cari panel hasil di seluruh layar.
            print("Area tidak ditandai -> mode OTOMATIS (mencari di seluruh layar).")
            print("Screenshot diambil dalam 5 detik, pindah ke jendela game sekarang...")
            import time
            time.sleep(5)
            penuh, _, _ = layar.ambil_semua_monitor()
            if layar.gelap(penuh):
                print("PERINGATAN: screenshot hitam. Ubah game ke mode Borderless/Windowed.")
            hasil = ocr.cari_di_layar(penuh, label, cfg["ocr"])
            umum.FOLDER_DATA.mkdir(exist_ok=True)
            if hasil.dps is None or not hasil.panel:
                penuh.save(umum.FOLDER_DATA / "tes_area.png")
                print("\nPanel hasil TIDAK ditemukan di layar.")
                print("Pastikan layar hasil Damage Challenge sedang tampil dan tidak tertutup jendela lain.")
                print(f"Yang dilihat bot disimpan di: {umum.FOLDER_DATA / 'tes_area.png'}")
                return 1
            x0, y0, x1, y1 = hasil.kotak
            penuh.crop((max(0, x0 - 50), max(0, y0 - 35), x1 + 50, y1 + 35)).save(umum.FOLDER_DATA / "tes_area.png")
            print(f"\nKETEMU. DPS = {umum.fmt(hasil.dps)} | Total DMG = {umum.fmt(hasil.total)} "
                  f"| Rekor = {umum.fmt(hasil.rekor)}")
            print(f"Potongan gambarnya: {umum.FOLDER_DATA / 'tes_area.png'}")
            print("Cocokkan angka di atas dengan yang ada di layar game.")
            return 0
        img = layar.ambil_area(profil["area"])
        umum.FOLDER_DATA.mkdir(exist_ok=True)
        simpan = umum.FOLDER_DATA / "tes_area.png"
        img.save(simpan)
        if layar.gelap(img):
            print("PERINGATAN: screenshot hitam. Ubah game ke mode Borderless/Windowed.")
        hasil = tampilkan(f"Screenshot area profil '{profil['nama']}'", img, label, cfg["ocr"])
        print(f"\nGambar yang dibaca disimpan di: {simpan}")
        if hasil.dps is None:
            print("Angka DPS TIDAK terbaca. Pastikan layar hasil Damage Challenge sedang tampil,")
            print("dan area mencakup tulisan 'DMG Per Second:' beserta angkanya.")
        else:
            print("Cocokkan angka di atas dengan yang ada di layar game.")
        return 0
    except ocr.OcrError as e:
        print("OCR GAGAL:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
