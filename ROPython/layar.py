"""Ambil screenshot. HANYA melihat layar, tidak mengirim input apa pun."""
from __future__ import annotations

import io

import mss
from PIL import Image, ImageChops, ImageStat


def _ke_pil(tangkapan) -> Image.Image:
    return Image.frombytes("RGB", tangkapan.size, tangkapan.bgra, "raw", "BGRX")


def ambil_area(area: dict) -> Image.Image:
    """Screenshot kotak area saja. Koordinat = piksel asli di seluruh desktop."""
    kotak = {k: int(area[k]) for k in ("left", "top", "width", "height")}
    with mss.mss() as sct:
        return _ke_pil(sct.grab(kotak))


def ambil_semua_monitor():
    """Screenshot gabungan semua monitor. Mengembalikan (gambar, left, top)."""
    with mss.mss() as sct:
        m = sct.monitors[0]
        return _ke_pil(sct.grab(m)), m["left"], m["top"]


def area_semua_monitor() -> dict:
    with mss.mss() as sct:
        m = sct.monitors[0]
        return {k: m[k] for k in ("left", "top", "width", "height")}


def ambil_layar_penuh(area: dict | None = None) -> Image.Image:
    """Screenshot satu monitor penuh: monitor tempat area berada.

    Kalau area belum diketahui, semua monitor diambil sekaligus.
    """
    with mss.mss() as sct:
        daftar = sct.monitors[1:] or sct.monitors
        pilih = sct.monitors[0]
        if area:
            cx = area["left"] + area["width"] // 2
            cy = area["top"] + area["height"] // 2
            for m in daftar:
                if m["left"] <= cx < m["left"] + m["width"] and m["top"] <= cy < m["top"] + m["height"]:
                    pilih = m
                    break
        return _ke_pil(sct.grab(pilih))


# ------------------------------------------------------------------ jendela game
# Hanya MENANYAKAN ke Windows "jendela bernama X ada di posisi mana" (sama seperti
# OBS/Discord mencari jendela). Tidak ada apa pun yang dikirim ke game.

def _user32():
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.WindowFromPoint.argtypes = [wintypes.POINT]
    u.WindowFromPoint.restype = wintypes.HWND
    u.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    u.GetAncestor.restype = wintypes.HWND
    return ctypes, wintypes, u


def jendela_game(judul: str) -> list[tuple[int, dict]]:
    """Cari jendela yang judulnya persis `judul` (tidak di-minimize).

    Mengembalikan daftar (id jendela, area isi jendela di layar), sudah dipotong
    supaya tidak keluar dari layar.
    """
    ctypes, wintypes, u = _user32()
    cari = judul.strip().casefold()
    ketemu: list[tuple[int, dict]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def periksa(hwnd, _):
        if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return True
        n = u.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.strip().casefold() != cari:
            return True
        r = wintypes.RECT()
        p = wintypes.POINT(0, 0)
        if u.GetClientRect(hwnd, ctypes.byref(r)) and u.ClientToScreen(hwnd, ctypes.byref(p)):
            if r.right > 0 and r.bottom > 0:
                ketemu.append((int(hwnd), {"left": p.x, "top": p.y, "width": r.right, "height": r.bottom}))
        return True

    u.EnumWindows(periksa, 0)
    with mss.mss() as sct:
        m = sct.monitors[0]
    hasil = []
    for hwnd, a in ketemu:
        x0, y0 = max(a["left"], m["left"]), max(a["top"], m["top"])
        x1 = min(a["left"] + a["width"], m["left"] + m["width"])
        y1 = min(a["top"] + a["height"], m["top"] + m["height"])
        if x1 - x0 > 50 and y1 - y0 > 50:
            hasil.append((hwnd, {"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0}))
    return hasil


def ambil_jendela(hwnd: int) -> Image.Image | None:
    """Ambil gambar ISI jendela game langsung dari Windows (PrintWindow), seperti "Window
    Capture" di OBS. Tetap kelihatan walaupun jendela game ketutup Telegram/WhatsApp/Chrome.
    Hanya MEMINTA gambar, tidak mengirim input apa pun ke game.
    Mengembalikan None kalau tidak bisa (hasilnya hitam) -> pakai screenshot layar biasa."""
    import ctypes
    from ctypes import wintypes
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    for fn in (u.GetDC, g.CreateCompatibleDC):
        fn.restype = ctypes.c_void_p
    g.CreateCompatibleBitmap.restype = ctypes.c_void_p
    u.GetDC.argtypes = [wintypes.HWND]
    u.ReleaseDC.argtypes = [wintypes.HWND, ctypes.c_void_p]
    u.PrintWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_uint]
    g.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    g.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    g.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    g.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    g.DeleteObject.argtypes = [ctypes.c_void_p]
    g.DeleteDC.argtypes = [ctypes.c_void_p]

    class _BMI(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32),
                    ("x", ctypes.c_int32), ("y", ctypes.c_int32), ("used", ctypes.c_uint32),
                    ("important", ctypes.c_uint32)]

    r = wintypes.RECT()
    if not u.GetClientRect(hwnd, ctypes.byref(r)) or r.right < 50 or r.bottom < 50:
        return None
    w, h = r.right, r.bottom
    hdc = u.GetDC(hwnd)
    if not hdc:
        return None
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    try:
        g.SelectObject(mdc, bmp)
        if not u.PrintWindow(hwnd, mdc, 3):  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
            return None
        bi = _BMI(ctypes.sizeof(_BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0):
            return None
    finally:
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        u.ReleaseDC(hwnd, hdc)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).copy()
    return None if gelap(img) else img


def game_di_depan(judul: str) -> bool:
    """True kalau jendela yang sedang aktif (di depan, menerima ketikan/klik) adalah jendela game.
    Hanya membaca judul jendela dari Windows, tidak menyentuh game."""
    ctypes, wintypes, u = _user32()
    u.GetForegroundWindow.restype = wintypes.HWND
    h = u.GetForegroundWindow()
    if not h:
        return False
    h = u.GetAncestor(h, 2) or h  # GA_ROOT
    n = u.GetWindowTextLengthW(h)
    if n <= 0:
        return False
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, buf, n + 1)
    return buf.value.strip().casefold() == judul.strip().casefold()


def titik_milik(x: int, y: int, daftar_hwnd: set[int]) -> bool:
    """True kalau titik (x, y) di layar memang menampilkan salah satu jendela game
    (bukan jendela lain yang menutupinya, misalnya WhatsApp/Telegram)."""
    ctypes, wintypes, u = _user32()
    h = u.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    if not h:
        return False
    akar = u.GetAncestor(h, 2) or h  # GA_ROOT
    return int(akar) in daftar_hwnd or int(h) in daftar_hwnd


def gelap(img: Image.Image) -> bool:
    """True kalau gambar nyaris hitam polos (layar mati / game fullscreen exclusive)."""
    stat = ImageStat.Stat(img.convert("L"))
    return stat.mean[0] < 12 and stat.stddev[0] < 4


def sidik(img: Image.Image) -> Image.Image:
    """Versi mini (96x54 abu-abu) untuk membandingkan dua screenshot dengan sangat cepat."""
    return img.convert("L").resize((96, 54), Image.BILINEAR)


def beda(a: Image.Image | None, b: Image.Image) -> float:
    """Rata-rata perbedaan piksel dua sidik (0 = persis sama, 255 = beda total)."""
    if a is None or a.size != b.size:
        return 255.0
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def ke_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def ke_jpg(img: Image.Image, kualitas: int = 85) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=kualitas)
    return buf.getvalue()
