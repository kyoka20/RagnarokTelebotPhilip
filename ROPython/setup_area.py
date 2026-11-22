"""SETUP AREA - tandai kotak hasil DPS di layar dengan drag mouse.

Script mengambil screenshot dulu, lalu menampilkan screenshot itu sebagai gambar
diam di jendela milik script sendiri. Drag mouse dilakukan DI ATAS GAMBAR ITU,
jadi game tidak menerima klik apa pun.

Cara pakai (atau klik 2_setup_area.bat):
  python setup_area.py                -> untuk profil aktif
  python setup_area.py "Nama Profil"  -> untuk profil lain (dibuat kalau belum ada)
"""
from __future__ import annotations

import copy
import sys
import time
import tkinter as tk

from PIL import ImageEnhance, ImageTk

import layar
import ocr
import umum

MIN_UKURAN = 20


class Penanda:
    def __init__(self, gambar, kiri: int, atas: int):
        self.gambar, self.kiri, self.atas = gambar, kiri, atas
        self.hasil: dict | None = None
        self.mulai: tuple[int, int] | None = None
        self.kotak: tuple[int, int, int, int] | None = None

        self.root = tk.Tk()
        self.root.overrideredirect(True)  # tanpa bingkai jendela
        self.root.geometry(f"{gambar.width}x{gambar.height}+{kiri}+{atas}")
        self.root.attributes("-topmost", True)
        self.root.configure(cursor="crosshair")

        self.kanvas = tk.Canvas(self.root, width=gambar.width, height=gambar.height, highlightthickness=0)
        self.kanvas.pack()
        # Gambar digelapkan sedikit supaya jelas ini mode "menandai", bukan game aslinya.
        self.foto_gelap = ImageTk.PhotoImage(ImageEnhance.Brightness(gambar).enhance(0.55))
        self.kanvas.create_image(0, 0, image=self.foto_gelap, anchor="nw")
        self.foto_terang = None
        self.id_terang = None
        self.id_kotak = self.kanvas.create_rectangle(0, 0, 0, 0, outline="#00ff66", width=2)
        self.id_teks = self.kanvas.create_text(
            20, 20, anchor="nw", fill="#ffff00", font=("Segoe UI", 14, "bold"),
            text=("DRAG mouse untuk mengotaki area hasil (dari 'Total DMG' sampai 'Highest Solo DMG Record').\n"
                  "ENTER = simpan   |   drag lagi = ulang   |   ESC = batal"),
        )

        self.kanvas.bind("<ButtonPress-1>", self.tekan)
        self.kanvas.bind("<B1-Motion>", self.geser)
        self.kanvas.bind("<ButtonRelease-1>", self.lepas)
        self.root.bind("<Return>", self.simpan)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.after(100, self.root.focus_force)

    def tekan(self, e):
        self.mulai = (e.x, e.y)

    def geser(self, e):
        if not self.mulai:
            return
        x0, y0 = self.mulai
        x1 = min(max(e.x, 0), self.gambar.width)
        y1 = min(max(e.y, 0), self.gambar.height)
        self.kotak = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        self.kanvas.coords(self.id_kotak, *self.kotak)

    def lepas(self, e):
        self.geser(e)
        if not self.kotak:
            return
        x0, y0, x1, y1 = self.kotak
        if x1 - x0 < MIN_UKURAN or y1 - y0 < MIN_UKURAN:
            return
        # Bagian yang dipilih ditampilkan terang supaya kelihatan apa yang akan dibaca.
        self.foto_terang = ImageTk.PhotoImage(self.gambar.crop(self.kotak))
        if self.id_terang:
            self.kanvas.delete(self.id_terang)
        self.id_terang = self.kanvas.create_image(x0, y0, image=self.foto_terang, anchor="nw")
        self.kanvas.tag_raise(self.id_kotak)
        self.kanvas.tag_raise(self.id_teks)

    def simpan(self, _=None):
        if not self.kotak:
            return
        x0, y0, x1, y1 = self.kotak
        if x1 - x0 < MIN_UKURAN or y1 - y0 < MIN_UKURAN:
            return
        self.hasil = {
            "left": self.kiri + x0, "top": self.atas + y0,
            "width": x1 - x0, "height": y1 - y0,
        }
        self.root.destroy()

    def jalankan(self) -> dict | None:
        self.root.mainloop()
        return self.hasil


def main() -> int:
    umum.siapkan_konsol()
    umum.aktifkan_dpi_aware()
    try:
        cfg = umum.muat_config()
    except umum.ConfigError as e:
        print("MASALAH CONFIG:", e)
        return 2

    nama = " ".join(sys.argv[1:]).strip()
    pid = umum.id_profil(nama) if nama else cfg["profil_aktif"]
    if pid not in cfg["profil"]:
        baru = copy.deepcopy(cfg["profil"][cfg["profil_aktif"]])
        baru["nama"], baru["area"] = nama, None
        cfg["profil"][pid] = baru
        print(f"Profil baru dibuat: {nama}")
    profil = cfg["profil"][pid]

    print(f"Setup area untuk profil: {profil['nama']}")
    print("Pastikan layar hasil Damage Challenge sedang TAMPIL di game.")
    print("Screenshot diambil dalam 3 detik...")
    time.sleep(3)
    gambar, kiri, atas = layar.ambil_semua_monitor()
    area = Penanda(gambar, kiri, atas).jalankan()
    if not area:
        print("Dibatalkan. Tidak ada yang diubah.")
        return 1

    # Muat ulang config sebelum menyimpan, supaya perubahan lain tidak tertimpa.
    cfg_baru = umum.muat_config()
    cfg_baru["profil"].setdefault(pid, profil)
    cfg_baru["profil"][pid]["area"] = area
    umum.simpan_config(cfg_baru)
    print(f"Area tersimpan: {area}")

    potong = gambar.crop((area["left"] - kiri, area["top"] - atas,
                          area["left"] - kiri + area["width"], area["top"] - atas + area["height"]))
    umum.FOLDER_DATA.mkdir(exist_ok=True)
    potong.save(umum.FOLDER_DATA / "pratinjau_area.png")
    try:
        hasil = ocr.baca_hasil(potong, profil.get("label", "DMG Per Second"), cfg_baru["ocr"])
        if hasil.dps is not None:
            print(f"Langsung dites: DPS terbaca = {umum.fmt(hasil.dps)}  <-- cocokkan dengan layar game")
        else:
            print("Langsung dites: angka DPS BELUM terbaca di area itu.")
            print("Coba ulangi dan kotaki lebih lebar (tulisan 'DMG Per Second:' harus ikut masuk).")
    except ocr.OcrError as e:
        print("OCR gagal:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
