"""Mode TRAIN: rekam layar game (hanya screenshot, tidak menyentuh game) untuk dipelajari.

/record_train -> mulai simpan gambar jendela game setiap kali layarnya BERUBAH.
/stop         -> berhenti, lalu tiap gambar dibaca (OCR) dan dikelompokkan per halaman.

Hasil per rekaman di data/_latih/<waktu>/:
  0001_204512.jpg ...   gambar jendela game
  rekaman.json          per gambar: jam, halaman, teks yang terbaca
Detail gem & efek set di halaman Enchant langsung DIPELAJARI otomatis (belajar.py) -> /db.
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import layar
import ocr
import umum

FOLDER_LATIH = umum.FOLDER_DATA / "_latih"
MAKS_MENIT = 60
MAKS_GAMBAR = 1500

# (nama halaman, kata kunci yang harus ada di teks layar) - dicek berurutan, yang pertama cocok dipakai
HALAMAN = [
    ("Detail gem (Enchant Stone)", ("Gem Stats",)),
    ("Ganti batu enchant", ("Replace Enchant Stone",)),
    ("Detail item", ("Overall Rati",)),
    ("Enchant", ("Enchant Stone Stats",)),
    ("Enchant", ("Gem Lv Up",)),
    ("Insert Card", ("Insert Card",)),
    ("Refine", ("Refine Lv", "Success Rate")),
    ("Status karakter", ("Character Info", "Base Stats")),
    ("Status karakter", ("Character Info", "DMG vs")),
    ("Info karakter", ("Character Info",)),
    ("Skills", ("Skill Points Left",)),
    ("Skills", ("Allocatable",)),
    ("Inventory", ("Inventory", "Dismantle")),
    ("Hasil Damage Challenge", ("DMG Per Second", "Total DMG")),
    ("Damage Challenge", ("Damage Challenge",)),
]


def jenis_halaman(teks: str) -> str:
    import bacabuild
    for nama, kunci in HALAMAN:
        if nama in ("Status karakter", "Info karakter") and bacabuild.halaman_status(teks):
            return "Status karakter"
        if all(k in teks for k in kunci):
            return nama
    return "Lainnya"


class Perekam:
    """Satu sesi rekaman. ambil_gambar() = fungsi yang mengembalikan gambar jendela game (atau None)."""

    def __init__(self, ambil_gambar, folder_induk: Path = FOLDER_LATIH, jeda: float = 1.0):
        self.ambil_gambar = ambil_gambar
        self.mulai = datetime.now()
        self.folder = folder_induk / self.mulai.strftime("%Y%m%d_%H%M%S")
        self.folder.mkdir(parents=True, exist_ok=True)
        self.jeda = jeda
        self.jumlah = 0
        self.alasan_berhenti = ""
        self._stop = threading.Event()
        self._sidik = None
        self._thread = threading.Thread(target=self._jalan, daemon=True, name="rekam-train")

    def mulai_rekam(self) -> None:
        self._thread.start()

    @property
    def aktif(self) -> bool:
        return self._thread.is_alive()

    def hentikan(self, alasan: str = "dihentikan") -> None:
        if not self.alasan_berhenti:
            self.alasan_berhenti = alasan
        self._stop.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=10)

    def _jalan(self) -> None:
        while not self._stop.is_set():
            if (datetime.now() - self.mulai).total_seconds() > MAKS_MENIT * 60:
                self.alasan_berhenti = self.alasan_berhenti or f"otomatis berhenti setelah {MAKS_MENIT} menit"
                break
            if self.jumlah >= MAKS_GAMBAR:
                self.alasan_berhenti = self.alasan_berhenti or f"otomatis berhenti setelah {MAKS_GAMBAR} gambar"
                break
            try:
                img = self.ambil_gambar()
            except Exception:
                img = None
            if img is not None:
                sidik = layar.sidik(img)
                if self._sidik is None or layar.beda(self._sidik, sidik) >= 1.0:  # hanya kalau layar berubah
                    self._sidik = sidik
                    self.jumlah += 1
                    img.convert("RGB").save(self.folder / f"{self.jumlah:04d}_{datetime.now():%H%M%S}.jpg", quality=85)
            self._stop.wait(self.jeda)

    def olah(self, cfg_ocr: dict) -> dict:
        """Baca semua gambar (OCR), kelompokkan per halaman, simpan rekaman.json. Hasil: ringkasan."""
        import belajar
        from PIL import Image
        data, hitung, bacaan = [], Counter(), []
        for f in sorted(self.folder.glob("*.jpg")):
            try:
                img = Image.open(f).convert("RGB")
                kata, _ = ocr._jalankan_mesin(img, cfg_ocr)
                baris = ocr._kelompokkan_baris(kata)
                teks = [" ".join(k.teks for k in b) for b in baris]
                if belajar.ada_enchant(" ".join(teks)):  # pelajari detail gem & efek set otomatis
                    b = belajar.baca_halaman(img, cfg_ocr, baris)
                    if b:
                        bacaan.append(b)
            except Exception as e:
                teks = [f"(OCR gagal: {e})"]
            halaman = jenis_halaman(" ".join(teks))
            hitung[halaman] += 1
            data.append({"file": f.name, "jam": f.stem.split("_")[-1], "halaman": halaman, "teks": teks})
        durasi = (datetime.now() - self.mulai).total_seconds()
        ringkas = {"mulai": self.mulai.strftime("%Y-%m-%d %H:%M:%S"), "durasi_detik": round(durasi),
                   "jumlah_gambar": len(data), "halaman": dict(hitung.most_common()),
                   "alasan_berhenti": self.alasan_berhenti, "folder": str(self.folder),
                   "dibaca_enchant": len(bacaan), "belajar": belajar.simpan(bacaan)}
        (self.folder / "rekaman.json").write_text(json.dumps({"ringkasan": ringkas, "gambar": data},
                                                             ensure_ascii=False, indent=1), encoding="utf-8")
        return ringkas


# ------------------------------------------------------------ kumpul otomatis (tanpa /record_train)
# Tiap halaman Enchant / Gem / Replace Enchant Stone yang BERUBAH saat bot memantau -> gambar disimpan
# + teks & bacaan, untuk bahan memperbaiki pembacaan nanti. Folder: data/_latih/otomatis/<YYYYMMDD>/
FOLDER_OTOMATIS = FOLDER_LATIH / "otomatis"
MAKS_OTOMATIS_HARI = 300     # gambar per hari
MAKS_OTOMATIS_MB = 1500      # total; lebih dari ini hari tertua dihapus


def simpan_otomatis(img, pid: str, teks: str, bacaan: dict | None) -> Path | None:
    """Simpan satu momen berkualitas. Hasil: path gambar, atau None kalau jatah hari ini habis."""
    kini = datetime.now()
    folder = FOLDER_OTOMATIS / kini.strftime("%Y%m%d")
    baru_hari = not folder.exists()
    folder.mkdir(parents=True, exist_ok=True)
    if baru_hari:
        _bersihkan_otomatis(folder.name)
    n = sum(1 for _ in folder.glob("*.jpg"))
    if n >= MAKS_OTOMATIS_HARI:
        return None
    aman = "".join(c for c in str(pid) if c.isalnum() or c in "-_")[:30] or "x"
    nama = f"{n + 1:04d}_{kini:%H%M%S}_{aman}.jpg"
    img.convert("RGB").save(folder / nama, quality=85)
    with open(folder / "catatan.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"file": nama, "jam": kini.strftime("%H:%M:%S"), "pid": pid,
                            "halaman": jenis_halaman(teks), "teks": teks, "bacaan": bacaan or {}},
                           ensure_ascii=False) + "\n")
    return folder / nama


def _bersihkan_otomatis(kecuali: str) -> None:
    hari = sorted(p for p in FOLDER_OTOMATIS.iterdir() if p.is_dir() and p.name != kecuali)
    total = sum(ukuran_mb(p) for p in hari)
    while hari and total > MAKS_OTOMATIS_MB:
        p = hari.pop(0)
        total -= ukuran_mb(p)
        for f in p.glob("*"):
            f.unlink(missing_ok=True)
        p.rmdir()


def info_otomatis() -> list[tuple[str, int, float]]:
    """(tanggal YYYYMMDD, jumlah gambar, MB) per hari, terbaru dulu."""
    if not FOLDER_OTOMATIS.exists():
        return []
    return [(p.name, sum(1 for _ in p.glob("*.jpg")), ukuran_mb(p))
            for p in sorted(FOLDER_OTOMATIS.iterdir(), reverse=True) if p.is_dir()]


def zip_otomatis(tanggal: str, batas_mb: float = 20) -> tuple[bytes, int, int]:
    """Zip satu hari (catatan + gambar sampai batas_mb; Telegram maks 50 MB, upload dibatasi 90 detik).
    Hasil: (isi zip, gambar masuk, total gambar)."""
    import io
    import zipfile
    folder = FOLDER_OTOMATIS / tanggal
    gambar = sorted(folder.glob("*.jpg"))
    buf, masuk, ukuran = io.BytesIO(), 0, 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        if (folder / "catatan.jsonl").exists():
            z.write(folder / "catatan.jsonl", f"{tanggal}/catatan.jsonl")
        for g in gambar:
            ukuran += g.stat().st_size
            if ukuran > batas_mb * 1e6:
                break
            z.write(g, f"{tanggal}/{g.name}")
            masuk += 1
    return buf.getvalue(), masuk, len(gambar)


def ukuran_mb(folder: Path) -> float:
    return sum(f.stat().st_size for f in folder.glob("*")) / 1e6


def rekaman_terakhir() -> Path | None:
    if not FOLDER_LATIH.exists():
        return None
    semua = sorted(p for p in FOLDER_LATIH.iterdir() if p.is_dir())
    return semua[-1] if semua else None


if __name__ == "__main__":  # uji cepat: python latih.py  -> ringkasan rekaman terakhir
    umum.siapkan_konsol()
    f = rekaman_terakhir()
    print(f, json.loads((f / "rekaman.json").read_text(encoding="utf-8"))["ringkasan"] if f and (f / "rekaman.json").exists() else "")
    time.sleep(0)
