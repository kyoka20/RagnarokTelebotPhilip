"""Gambar RAPOR premium, GRAFIK progres DPS, dan HALL OF FAME (/rekor) untuk Philip & klien.

Hanya mengolah data & screenshot yang sudah tersimpan. Tidak menyentuh game.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import catatan
import umum

LEBAR = 1280
BG = (11, 15, 30)
KARTU = (20, 27, 50)
KARTU2 = (26, 35, 64)
GARIS = (48, 60, 102)
PUTIH = (244, 246, 255)
ABU = (148, 160, 198)
HIJAU = (52, 211, 153)
CYAN = (56, 189, 248)
MERAH = (248, 113, 113)
EMAS = (250, 204, 21)
UNGU = (167, 139, 250)
ORANYE = (251, 146, 60)

_FONT_WIN = Path("C:/Windows/Fonts")


def _font(ukuran: int, tebal: bool = False) -> ImageFont.FreeTypeFont:
    for nama in (("segoeuib.ttf", "arialbd.ttf") if tebal else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(str(_FONT_WIN / nama), ukuran)
        except OSError:
            continue
    return ImageFont.load_default(ukuran)


def _tengah(d: ImageDraw.ImageDraw, cx: int, y: int, teks: str, font, warna) -> None:
    w = d.textlength(teks, font=font)
    d.text((cx - w / 2, y), teks, font=font, fill=warna)


def _gradasi_v(img: Image.Image, x0: int, y0: int, x1: int, y1: int, c1: tuple, c2: tuple) -> None:
    d = ImageDraw.Draw(img)
    h = max(1, y1 - y0)
    for dy in range(h):
        t = dy / h
        c = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        d.line((x0, y0 + dy, x1, y0 + dy), fill=c)


def _rank_badge(naik: float, tembus: bool = False) -> tuple[str, tuple]:
    if naik >= 100:
        return "RANK S+  •  GODLIKE BOOST", EMAS
    if naik >= 50:
        return "RANK S  •  ELITE BUILD", UNGU
    if naik >= 25:
        return "RANK A+  •  PRO UPGRADE", HIJAU
    if naik >= 10:
        return "RANK A  •  SOLID GAIN", CYAN
    if naik > 0:
        return "BUILD PROGRESS", CYAN
    return "BUILD REPORT", ABU


def _foto(pid: str, data: dict | None, lebar: int, tinggi: int, label_pojok: str = "", warna_label=CYAN) -> Image.Image:
    kanvas = Image.new("RGB", (lebar, tinggi), (14, 19, 36))
    f = catatan.folder_profil(pid) / "gambar" / data["gambar"] if data and data.get("gambar") else None
    if not f or not f.exists():
        d = ImageDraw.Draw(kanvas)
        _tengah(d, lebar // 2, tinggi // 2 - 14, "foto belum tersimpan", _font(24), ABU)
    else:
        img = Image.open(f).convert("RGB")
        img.thumbnail((lebar, tinggi), Image.LANCZOS)
        kanvas.paste(img, ((lebar - img.width) // 2, (tinggi - img.height) // 2))
    d = ImageDraw.Draw(kanvas)
    d.rectangle((0, 0, lebar - 1, tinggi - 1), outline=GARIS, width=2)
    if label_pojok:
        fnt = _font(18, True)
        tw = int(d.textlength(label_pojok, font=fnt)) + 24
        d.rounded_rectangle((12, 12, 12 + tw, 44), 8, fill=(11, 15, 30), outline=warna_label, width=2)
        d.text((24, 17), label_pojok, font=fnt, fill=warna_label)
    return kanvas


def _gambar_kurva(img: Image.Image, box: tuple[int, int, int, int], data: list[dict], target: int = 0) -> None:
    """Gambar grafik kurva progres DPS (area + garis + titik awal/puncak/akhir + garis target)."""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, 16, fill=KARTU, outline=GARIS, width=2)
    if len(data) < 2:
        _tengah(d, (x0 + x1) // 2, (y0 + y1) // 2 - 12, "Butuh minimal 2 test untuk grafik tren", _font(22), ABU)
        return

    pad_l, pad_r, pad_t, pad_b = 115, 40, 36, 42
    gx0, gy0, gx1, gy1 = x0 + pad_l, y0 + pad_t, x1 - pad_r, y1 - pad_b
    gw, gh = max(1, gx1 - gx0), max(1, gy1 - gy0)

    vals = [r["dps"] for r in data]
    vmin = min(vals) * 0.92
    vmax = max(vals) * 1.06
    if vmax <= vmin:
        vmax = vmin + 1

    def px(i: int) -> int:
        return int(gx0 + i / (len(vals) - 1) * gw)

    def py(v: float) -> int:
        return int(gy1 - (v - vmin) / (vmax - vmin) * gh)

    # Grid horizontal (3 garis)
    f_kecil = _font(17)
    for frac in (0.0, 0.5, 1.0):
        gv = vmin + frac * (vmax - vmin)
        gy = py(gv)
        d.line((gx0, gy, gx1, gy), fill=(33, 43, 74), width=1)
        lbl = f"{gv / 1e6:.2f}jt" if gv >= 1e6 else f"{gv / 1e3:.0f}k"
        d.text((x0 + 18, gy - 10), lbl, font=f_kecil, fill=ABU)

    pts = [(px(i), py(v)) for i, v in enumerate(vals)]

    # Area semi-transparan di bawah kurva
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    poly = [(gx0, gy1)] + pts + [(gx1, gy1)]
    od.polygon(poly, fill=(56, 189, 248, 38))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))
    d = ImageDraw.Draw(img)

    # Garis utama
    d.line(pts, fill=CYAN, width=4, joint="curve")

    # Titik awal, puncak, akhir
    idx_max = max(range(len(vals)), key=lambda i: vals[i])
    for idx, warna, r in ((0, PUTIH, 6), (len(vals) - 1, HIJAU, 6), (idx_max, EMAS, 8)):
        cx, cy = pts[idx]
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=warna, outline=BG, width=2)

    # Label puncak
    mx, my = pts[idx_max]
    lbl_max = f"REKOR {umum.fmt(vals[idx_max])}"
    f_max = _font(17, True)
    lw = d.textlength(lbl_max, font=f_max)
    lx = min(max(gx0, mx - lw / 2), gx1 - lw)
    ly = max(y0 + 8, my - 30)
    d.text((lx, ly), lbl_max, font=f_max, fill=EMAS)

    # Sumbu X
    d.text((gx0, gy1 + 10), f"Test #1 ({data[0]['waktu']:%d/%m})", font=f_kecil, fill=ABU)
    t_end = f"Test #{len(data)} ({data[-1]['waktu']:%d/%m %H:%M})"
    d.text((gx1 - d.textlength(t_end, font=f_kecil), gy1 + 10), t_end, font=f_kecil, fill=ABU)


def buat(pid: str, profil: dict, catatan_kaki: str = "") -> tuple[bytes, dict] | None:
    """Rapor premium: gradient header, rank badge, 3 kartu angka, progress bar target,
    grafik kurva tren DPS, dan foto SEBELUM vs SESUDAH."""
    semua = catatan.baca_ok(pid)
    if len(semua) < 2:
        return None
    awal = semua[0]
    terbaik = max(semua, key=lambda x: x["dps"])
    target = int(profil.get("target") or 0)
    naik = (terbaik["dps"] - awal["dps"]) / awal["dps"] * 100 if awal["dps"] else 0.0

    tinggi_foto = 330
    tinggi_grafik = 210 if len(semua) >= 2 else 0
    H = 158 + 185 + 16 + (tinggi_grafik + 24 if tinggi_grafik else 0) + 52 + tinggi_foto + 96
    img = Image.new("RGB", (LEBAR, H), BG)

    # Header gradasi
    _gradasi_v(img, 0, 0, LEBAR, 148, (24, 34, 68), (15, 21, 44))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 144, LEBAR, 148), fill=EMAS if naik >= 50 else (HIJAU if naik > 0 else CYAN))

    # Badge rank di kanan atas
    badge_txt, badge_col = _rank_badge(naik)
    f_badge = _font(20, True)
    bw = int(d.textlength(badge_txt, font=f_badge)) + 34
    d.rounded_rectangle((LEBAR - 40 - bw, 22, LEBAR - 40, 62), 20, fill=(14, 19, 38), outline=badge_col, width=2)
    _tengah(d, LEBAR - 40 - bw // 2, 29, badge_txt, f_badge, badge_col)

    d.text((40, 20), "RAPOR PROGRES BUILD DPS", font=_font(22, True), fill=EMAS)
    nick = str(profil.get("nick") or profil.get("nama") or pid)
    d.text((40, 50), nick, font=_font(52, True), fill=PUTIH)
    info = "  •  ".join(x for x in (str(profil.get("job") or ""),
                                    f"ID {profil['id_game']}" if profil.get("id_game") else "") if x)
    if info:
        d.text((LEBAR - 40 - d.textlength(info, font=_font(25)), 82), info, font=_font(25), fill=ABU)

    # Tiga kartu angka dengan aksen garis atas
    y = 172
    kotak_w, jarak = 380, 30
    isi = [
        ("DPS AWAL", umum.fmt(awal["dps"]), f"{awal['waktu']:%d/%m/%Y %H:%M}", PUTIH, CYAN),
        ("DPS TERBAIK", umum.fmt(terbaik["dps"]), f"{terbaik['waktu']:%d/%m/%Y %H:%M}", HIJAU, HIJAU),
        ("TOTAL KENAIKAN", f"{naik:+.1f}%".replace(".", ","),
         umum.fmt_selisih(terbaik["dps"] - awal["dps"]), EMAS if naik >= 0 else MERAH, EMAS if naik >= 0 else MERAH),
    ]
    for i, (judul, angka, bawah, warna, aksen) in enumerate(isi):
        x0 = 40 + i * (kotak_w + jarak)
        d.rounded_rectangle((x0, y, x0 + kotak_w, y + 162), 18, fill=KARTU, outline=GARIS, width=2)
        d.rounded_rectangle((x0 + 28, y, x0 + kotak_w - 28, y + 6), 3, fill=aksen)
        cx = x0 + kotak_w // 2
        _tengah(d, cx, y + 20, judul, _font(21, True), ABU)
        _tengah(d, cx, y + 54, angka, _font(52, True), warna)
        _tengah(d, cx, y + 122, bawah, _font(20), ABU)

    y += 186

    # Kurva progres DPS (jika >= 2 test)
    if tinggi_grafik:
        _gambar_kurva(img, (40, y, LEBAR - 40, y + tinggi_grafik), semua)
        d = ImageDraw.Draw(img)
        y += tinggi_grafik + 24

    # Foto sebelum / sesudah
    lebar_foto = (LEBAR - 40 * 2 - 30) // 2
    for i, (judul, badge, warna_b, data) in enumerate((
        ("SEBELUM", "BEFORE", ABU, awal),
        ("SESUDAH", "AFTER  •  BEST", HIJAU, terbaik),
    )):
        x0 = 40 + i * (lebar_foto + 30)
        d.text((x0, y), f"{judul}  ({data['waktu']:%d/%m %H:%M})", font=_font(22, True), fill=ABU)
        img.paste(_foto(pid, data, lebar_foto, tinggi_foto, badge, warna_b), (x0, y + 36))

    # Kaki
    y = y + 36 + tinggi_foto + 24
    d.line((40, y, LEBAR - 40, y), fill=GARIS, width=2)
    kiri = f"{len(semua)} kali test  •  {awal['waktu']:%d/%m/%Y} – {semua[-1]['waktu']:%d/%m/%Y}"
    d.text((40, y + 18), kiri, font=_font(22), fill=ABU)
    kanan = catatan_kaki or f"dibuat {datetime.now():%d/%m/%Y %H:%M}"
    d.text((LEBAR - 40 - d.textlength(kanan, font=_font(22, True)), y + 18), kanan,
           font=_font(22, True), fill=EMAS)

    ringkas = {"awal": awal, "terbaik": terbaik, "naik": naik, "jumlah": len(semua), "target": target}
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue(), ringkas


# ------------------------------------------------------------ /grafik

def buat_grafik(pid: str, profil: dict) -> bytes | None:
    """Gambar grafik HD perjalanan DPS 1 karakter (/grafik)."""
    semua = catatan.baca_ok(pid)
    if len(semua) < 2:
        return None
    awal = semua[0]
    terbaik = max(semua, key=lambda x: x["dps"])
    akhir = semua[-1]
    target = int(profil.get("target") or 0)
    naik = (terbaik["dps"] - awal["dps"]) / awal["dps"] * 100 if awal["dps"] else 0.0
    rata5 = round(sum(r["dps"] for r in semua[-5:]) / min(5, len(semua)))

    H = 680
    img = Image.new("RGB", (LEBAR, H), BG)
    _gradasi_v(img, 0, 0, LEBAR, 118, (24, 34, 68), (15, 21, 44))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 114, LEBAR, 118), fill=CYAN)

    nick = str(profil.get("nick") or profil.get("nama") or pid)
    d.text((40, 18), "GRAFIK PERJALANAN DPS", font=_font(20, True), fill=CYAN)
    d.text((40, 46), nick + (f"  ({profil['job']})" if profil.get("job") else ""), font=_font(40, True), fill=PUTIH)
    kanan = f"{len(semua)} test  •  {naik:+.1f}%".replace(".", ",")
    d.text((LEBAR - 40 - d.textlength(kanan, font=_font(28, True)), 52), kanan, font=_font(28, True), fill=HIJAU if naik >= 0 else MERAH)

    _gambar_kurva(img, (40, 142, LEBAR - 40, 515), semua, target)
    d = ImageDraw.Draw(img)

    # 4 kotak ringkasan bawah
    y = 538
    w4 = (LEBAR - 80 - 60) // 4
    stat_bawah = [
        ("AWAL", umum.fmt(awal["dps"]), PUTIH),
        ("REKOR PUNCAK", umum.fmt(terbaik["dps"]), EMAS),
        ("TERAKHIR", umum.fmt(akhir["dps"]), HIJAU),
        ("RATA-RATA 5 TERAKHIR", umum.fmt(rata5), CYAN),
    ]
    for i, (lbl, val, col) in enumerate(stat_bawah):
        x0 = 40 + i * (w4 + 20)
        d.rounded_rectangle((x0, y, x0 + w4, y + 108), 14, fill=KARTU, outline=GARIS, width=2)
        _tengah(d, x0 + w4 // 2, y + 16, lbl, _font(18, True), ABU)
        _tengah(d, x0 + w4 // 2, y + 48, val, _font(36, True), col)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


# ------------------------------------------------------------ /rekor (Hall of Fame Philip)

def _pangkat_philip(tembus: int, total_klien: int) -> tuple[str, tuple]:
    if tembus >= 30:
        return "MYTHIC DPS ARCHITECT", EMAS
    if tembus >= 15:
        return "GRANDMASTER BUILDER", UNGU
    if tembus >= 7:
        return "ELITE DPS SPECIALIST", HIJAU
    if tembus >= 3 or total_klien >= 10:
        return "PRO BUILDER", CYAN
    return "RISING BUILDER", ORANYE


def _hitung_streak(hari_aktif: set) -> int:
    if not hari_aktif:
        return 0
    hari = datetime.now().date()
    if hari not in hari_aktif:
        hari -= timedelta(days=1)
    streak = 0
    while hari in hari_aktif:
        streak += 1
        hari -= timedelta(days=1)
    return streak


def buat_hof(daftar_profil: list[tuple[str, dict]], catatan_kaki: str = "") -> tuple[bytes, dict] | None:
    """Poster Hall of Fame & motivasi Philip (/rekor): total klien, target tembus, streak,
    Top 5 kenaikan % terbesar, dan Top 5 DPS tertinggi."""
    ringkas_klien = []
    total_test = 0
    hari_aktif = set()
    tembus_cnt = 0

    for pid, p in daftar_profil:
        if pid == "akun1" and len(daftar_profil) > 1:
            continue
        ok = catatan.baca_ok(pid)
        if not ok:
            continue
        total_test += len(ok)
        for r in ok:
            hari_aktif.add(r["waktu"].date())
        awal = ok[0]["dps"]
        terbaik = max(r["dps"] for r in ok)
        naik = (terbaik - awal) / awal * 100 if awal else 0.0
        target = int(p.get("target") or 0)
        if target and terbaik >= target:
            tembus_cnt += 1
        ringkas_klien.append({
            "nama": str(p.get("nick") or p.get("nama") or pid),
            "job": str(p.get("job") or ""),
            "awal": awal,
            "terbaik": terbaik,
            "naik": naik,
            "jumlah": len(ok),
        })

    if not ringkas_klien:
        return None

    streak = _hitung_streak(hari_aktif)
    rata_naik = sum(k["naik"] for k in ringkas_klien if k["jumlah"] >= 2) / max(1, sum(1 for k in ringkas_klien if k["jumlah"] >= 2))
    top_naik = sorted([k for k in ringkas_klien if k["jumlah"] >= 2], key=lambda k: -k["naik"])[:5]
    top_dps = sorted(ringkas_klien, key=lambda k: -k["terbaik"])[:5]
    pangkat, col_pangkat = _pangkat_philip(tembus_cnt, len(ringkas_klien))

    H = 880
    img = Image.new("RGB", (LEBAR, H), BG)
    _gradasi_v(img, 0, 0, LEBAR, 150, (38, 26, 74), (15, 21, 44))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 146, LEBAR, 150), fill=EMAS)

    d.text((40, 22), "HALL OF FAME  •  REKOR JASA BUILD DPS", font=_font(22, True), fill=EMAS)
    d.text((40, 54), pangkat, font=_font(48, True), fill=PUTIH)

    badge_s = f"STREAK {streak} HARI" if streak else f"{len(hari_aktif)} HARI AKTIF"
    f_b = _font(22, True)
    bw = int(d.textlength(badge_s, font=f_b)) + 36
    d.rounded_rectangle((LEBAR - 40 - bw, 46, LEBAR - 40, 92), 22, fill=(14, 19, 38), outline=ORANYE, width=2)
    _tengah(d, LEBAR - 40 - bw // 2, 55, badge_s, f_b, ORANYE)

    # 4 kartu statistik global
    y = 176
    w4 = (LEBAR - 80 - 60) // 4
    kpi = [
        ("TOTAL KLIEN", str(len(ringkas_klien)), f"{total_test:,} kali test".replace(",", "."), CYAN),
        ("TARGET TEMBUS", str(tembus_cnt), f"dari {len(ringkas_klien)} klien", HIJAU),
        ("RATA-RATA NAIK", f"+{rata_naik:.1f}%".replace(".", ","), "per klien (≥2 test)", EMAS),
        ("DPS TERTINGGI", umum.fmt(top_dps[0]["terbaik"]), top_dps[0]["nama"], UNGU),
    ]
    for i, (lbl, val, sub, col) in enumerate(kpi):
        x0 = 40 + i * (w4 + 20)
        d.rounded_rectangle((x0, y, x0 + w4, y + 148), 16, fill=KARTU, outline=GARIS, width=2)
        d.rounded_rectangle((x0 + 24, y, x0 + w4 - 24, y + 5), 3, fill=col)
        _tengah(d, x0 + w4 // 2, y + 18, lbl, _font(19, True), ABU)
        _tengah(d, x0 + w4 // 2, y + 50, val, _font(42, True), col)
        _tengah(d, x0 + w4 // 2, y + 108, sub, _font(18), ABU)

    # Dua panel leaderboard: kiri = Top 5 Kenaikan %, kanan = Top 5 DPS Tertinggi
    y = 352
    pw = (LEBAR - 80 - 30) // 2
    ph = 430
    medali_col = [EMAS, (203, 213, 225), ORANYE, CYAN, ABU]

    for idx_panel, (judul, col_j, daftar, mode) in enumerate((
        ("TOP 5 KENAIKAN DPS TERBESAR", HIJAU, top_naik, "naik"),
        ("TOP 5 REKOR DPS TERTINGGI", EMAS, top_dps, "dps"),
    )):
        x0 = 40 + idx_panel * (pw + 30)
        d.rounded_rectangle((x0, y, x0 + pw, y + ph), 18, fill=KARTU, outline=GARIS, width=2)
        d.text((x0 + 26, y + 22), judul, font=_font(23, True), fill=col_j)
        d.line((x0 + 24, y + 60, x0 + pw - 24, y + 60), fill=GARIS, width=1)
        for rank, item in enumerate(daftar, 1):
            ry = y + 76 + (rank - 1) * 68
            d.rounded_rectangle((x0 + 22, ry, x0 + pw - 22, ry + 56), 12, fill=KARTU2)
            mc = medali_col[rank - 1]
            d.rounded_rectangle((x0 + 32, ry + 10, x0 + 68, ry + 46), 8, fill=(14, 19, 38), outline=mc, width=2)
            _tengah(d, x0 + 50, ry + 15, f"#{rank}", _font(20, True), mc)
            nm = item["nama"][:18]
            d.text((x0 + 82, ry + 8), nm, font=_font(22, True), fill=PUTIH)
            sub = (item["job"] + " • " if item["job"] else "") + f"{umum.fmt(item['awal'])} → {umum.fmt(item['terbaik'])}"
            d.text((x0 + 82, ry + 34), sub, font=_font(16), fill=ABU)
            if mode == "naik":
                kanan_v = f"{item['naik']:+.1f}%".replace(".", ",")
                vc = HIJAU
            else:
                kanan_v = umum.fmt(item["terbaik"])
                vc = EMAS
            d.text((x0 + pw - 36 - d.textlength(kanan_v, font=_font(25, True)), ry + 14), kanan_v, font=_font(25, True), fill=vc)

    # Kaki
    y = 812
    d.line((40, y, LEBAR - 40, y), fill=GARIS, width=2)
    d.text((40, y + 18), f"Terus gas racik!  •  {datetime.now():%d/%m/%Y %H:%M}", font=_font(21), fill=ABU)
    kanan = catatan_kaki or "RO DPS Monitor"
    d.text((LEBAR - 40 - d.textlength(kanan, font=_font(21, True)), y + 18), kanan, font=_font(21, True), fill=EMAS)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue(), {"klien": len(ringkas_klien), "tembus": tembus_cnt, "test": total_test, "streak": streak, "pangkat": pangkat}
