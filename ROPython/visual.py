"""Fitur visual & animasi untuk produktivitas dan promosi Philip:
  • /gif   -> Animasi GIF Before -> Counter Roll-up -> After (siap forward klien / WA Story)
  • /story -> Poster vertikal 9:16 (1080x1920) siap upload WA Status / TikTok / IG Story
  • /papan -> Dashboard Kanban visual antrean orderan (Prioritas Kerja | Siap Ditagih | Lunas)
"""
from __future__ import annotations

import io
from datetime import datetime

from PIL import Image, ImageDraw

import catatan
import rapor
import umum

BG = rapor.BG
KARTU = rapor.KARTU
KARTU2 = rapor.KARTU2
GARIS = rapor.GARIS
PUTIH = rapor.PUTIH
ABU = rapor.ABU
HIJAU = rapor.HIJAU
CYAN = rapor.CYAN
MERAH = rapor.MERAH
EMAS = rapor.EMAS
UNGU = rapor.UNGU
ORANYE = rapor.ORANYE


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - max(0.0, min(1.0, t))) ** 3


# ------------------------------------------------------------ 1. /gif (Animasi Before -> After)

def buat_gif(pid: str, profil: dict, catatan_kaki: str = "") -> tuple[bytes, dict] | None:
    """Animasi GIF ringan (~4.5 detik) transisi BEFORE -> counter roll-up -> AFTER."""
    semua = catatan.baca_ok(pid)
    if len(semua) < 2:
        return None
    awal = semua[0]
    terbaik = max(semua, key=lambda x: x["dps"])
    naik = (terbaik["dps"] - awal["dps"]) / awal["dps"] * 100 if awal["dps"] else 0.0
    nick = str(profil.get("nick") or profil.get("nama") or pid)
    job = str(profil.get("job") or "")
    badge_txt, badge_col = rapor._rank_badge(naik)

    W, H = 900, 520
    fw, fh = 410, 240
    foto_awal = rapor._foto(pid, awal, fw, fh, "BEFORE", ABU)
    foto_akhir = rapor._foto(pid, terbaik, fw, fh, "AFTER • BEST", HIJAU)

    # Buat latar dasar sekali saja biar render super cepat
    dasar = Image.new("RGB", (W, H), BG)
    rapor._gradasi_v(dasar, 0, 0, W, 94, (26, 36, 74), (14, 20, 42))
    dd = ImageDraw.Draw(dasar)
    dd.rectangle((0, 91, W, 94), fill=EMAS if naik >= 50 else (HIJAU if naik > 0 else CYAN))
    dd.text((28, 14), "PROGRES BUILD DPS", font=rapor._font(16, True), fill=EMAS)
    dd.text((28, 36), nick + (f"  •  {job}" if job else ""), font=rapor._font(34, True), fill=PUTIH)
    # Kaki
    dd.line((28, H - 44, W - 28, H - 44), fill=GARIS, width=1)
    dd.text((28, H - 32), f"{len(semua)} test  •  {awal['waktu']:%d/%m} – {terbaik['waktu']:%d/%m}",
            font=rapor._font(16), fill=ABU)
    kanan = catatan_kaki or "RO DPS Monitor"
    dd.text((W - 28 - dd.textlength(kanan, font=rapor._font(16, True)), H - 32),
            kanan, font=rapor._font(16, True), fill=EMAS)

    frames: list[Image.Image] = []
    durations: list[int] = []

    def render_frame(progress: float, fase: str) -> Image.Image:
        img = dasar.copy()
        d = ImageDraw.Draw(img)
        cur_dps = int(round(awal["dps"] + (terbaik["dps"] - awal["dps"]) * progress))
        cur_naik = naik * progress

        # Kiri: screenshot (fase awal = BEFORE, tengah = blend, akhir = AFTER)
        if fase == "before":
            img.paste(foto_awal, (28, 118))
        elif fase == "after":
            img.paste(foto_akhir, (28, 118))
        else:
            blended = Image.blend(foto_awal, foto_akhir, progress)
            img.paste(blended, (28, 118))

        # Kanan: panel angka animasi
        rx0, ry0, rx1, ry1 = 460, 118, W - 28, 358
        d.rounded_rectangle((rx0, ry0, rx1, ry1), 16, fill=KARTU, outline=HIJAU if fase == "after" and naik > 0 else GARIS, width=2)
        cx = (rx0 + rx1) // 2

        lbl_atas = "DPS AWAL" if fase == "before" else ("DPS TERBAIK" if fase == "after" else "BOOSTING DPS...")
        col_atas = ABU if fase == "before" else (HIJAU if fase == "after" else CYAN)
        rapor._tengah(d, cx, ry0 + 18, lbl_atas, rapor._font(18, True), col_atas)

        col_num = PUTIH if fase == "before" else (HIJAU if fase == "after" else CYAN)
        rapor._tengah(d, cx, ry0 + 52, umum.fmt(cur_dps), rapor._font(52, True), col_num)

        if progress > 0.01:
            t_naik = f"{cur_naik:+.1f}%".replace(".", ",")
            rapor._tengah(d, cx, ry0 + 124, t_naik, rapor._font(32, True), EMAS if cur_naik >= 0 else MERAH)
            rapor._tengah(d, cx, ry0 + 166, umum.fmt_selisih(cur_dps - awal["dps"]), rapor._font(18), ABU)
        else:
            rapor._tengah(d, cx, ry0 + 132, f"Mulai {awal['waktu']:%d/%m/%Y %H:%M}", rapor._font(18), ABU)

        if fase == "after":
            f_b = rapor._font(16, True)
            bw = int(d.textlength(badge_txt, font=f_b)) + 26
            d.rounded_rectangle((cx - bw // 2, ry0 + 198, cx + bw // 2, ry0 + 226), 14,
                                fill=(12, 17, 34), outline=badge_col, width=2)
            rapor._tengah(d, cx, ry0 + 203, badge_txt, f_b, badge_col)

        # Progress bar boost (Awal -> Terbaik, tanpa tulisan Target)
        by0, by1 = 380, 454
        d.rounded_rectangle((28, by0, W - 28, by1), 14, fill=KARTU, outline=GARIS, width=2)
        col_bar = HIJAU if fase == "after" else CYAN
        t_kiri = f"DPS AWAL {umum.fmt(awal['dps'])}   →   DPS TERBAIK {umum.fmt(terbaik['dps'])}"
        d.text((48, by0 + 12), t_kiri, font=rapor._font(18, True), fill=col_bar)
        t_kanan = f"{cur_naik:+.1f}%".replace(".", ",") if progress > 0.01 else "START"
        d.text((W - 48 - d.textlength(t_kanan, font=rapor._font(18, True)), by0 + 12), t_kanan,
               font=rapor._font(18, True), fill=EMAS if progress > 0.01 else ABU)
        bx0, bx1 = 48, W - 48
        d.rounded_rectangle((bx0, by0 + 44, bx1, by0 + 58), 7, fill=(12, 17, 34))
        fw_bar = max(12, int((bx1 - bx0) * max(0.06, progress)))
        d.rounded_rectangle((bx0, by0 + 44, bx0 + fw_bar, by0 + 58), 7, fill=col_bar)

        return img.convert("P", palette=Image.ADAPTIVE, colors=256)

    # Susun 18 frame mulus (~4.5 detik loop)
    frames.append(render_frame(0.0, "before"))
    durations.append(1000)

    steps = 12
    for i in range(1, steps + 1):
        p = _ease_out(i / steps)
        frames.append(render_frame(p, "boost"))
        durations.append(95)

    frames.append(render_frame(1.0, "after"))
    durations.append(2200)

    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    return buf.getvalue(), {"awal": awal["dps"], "terbaik": terbaik["dps"], "naik": naik}


# ------------------------------------------------------------ 2. /story (Poster 9:16 WA Status / TikTok)

def buat_story(pid: str, profil: dict, catatan_kaki: str = "") -> tuple[bytes, dict] | None:
    """Poster vertikal 1080x1920 (9:16) bergaya esports untuk WA Status / IG Story / TikTok."""
    semua = catatan.baca_ok(pid)
    if len(semua) < 2:
        return None
    awal = semua[0]
    terbaik = max(semua, key=lambda x: x["dps"])
    naik = (terbaik["dps"] - awal["dps"]) / awal["dps"] * 100 if awal["dps"] else 0.0
    nick = str(profil.get("nick") or profil.get("nama") or pid)
    job = str(profil.get("job") or "")
    badge_txt, badge_col = rapor._rank_badge(naik)

    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), BG)
    rapor._gradasi_v(img, 0, 0, W, 240, (30, 42, 86), (13, 19, 38))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 234, W, 240), fill=EMAS if naik >= 50 else (HIJAU if naik > 0 else CYAN))

    # Header
    rapor._tengah(d, W // 2, 34, "BEFORE  →  AFTER  BUILD DPS", rapor._font(26, True), EMAS)
    rapor._tengah(d, W // 2, 74, nick, rapor._font(64, True), PUTIH)
    sub_h = "  •  ".join(x for x in (job, f"{len(semua)} kali test") if x)
    rapor._tengah(d, W // 2, 152, sub_h, rapor._font(26), ABU)

    f_b = rapor._font(22, True)
    bw = int(d.textlength(badge_txt, font=f_b)) + 44
    d.rounded_rectangle((W // 2 - bw // 2, 192, W // 2 + bw // 2, 228), 18, fill=(11, 15, 30), outline=badge_col, width=2)
    rapor._tengah(d, W // 2, 197, badge_txt, f_b, badge_col)

    # Foto BEFORE
    y = 272
    d.text((54, y), f"SEBELUM  ({awal['waktu']:%d/%m/%Y %H:%M})", font=rapor._font(26, True), fill=ABU)
    img.paste(rapor._foto(pid, awal, W - 108, 430, "BEFORE", ABU), (54, y + 40))

    # Banner Boost Tengah (High Impact, tanpa Target)
    y = 770
    d.rounded_rectangle((54, y, W - 54, y + 290), 24, fill=KARTU, outline=HIJAU if naik >= 0 else CYAN, width=3)
    d.rounded_rectangle((120, y, W - 120, y + 7), 4, fill=EMAS if naik >= 0 else CYAN)

    rapor._tengah(d, W // 2, y + 32, f"{umum.fmt(awal['dps'])}   →   {umum.fmt(terbaik['dps'])}",
                  rapor._font(46, True), PUTIH)
    rapor._tengah(d, W // 2, y + 104, f"{naik:+.1f}%".replace(".", ","),
                  rapor._font(96, True), HIJAU if naik >= 0 else MERAH)
    rapor._tengah(d, W // 2, y + 220, f"Selisih {umum.fmt_selisih(terbaik['dps'] - awal['dps'])} DPS",
                  rapor._font(30, True), EMAS)

    # Foto AFTER
    y = 1094
    d.text((54, y), f"SESUDAH  ({terbaik['waktu']:%d/%m/%Y %H:%M})", font=rapor._font(26, True), fill=HIJAU)
    img.paste(rapor._foto(pid, terbaik, W - 108, 445, "AFTER • BEST", HIJAU), (54, y + 40))

    # Mini Kurva Progres
    if len(semua) >= 2:
        rapor._gambar_kurva(img, (54, 1608, W - 54, 1812), semua)
        d = ImageDraw.Draw(img)

    # Kaki watermark
    d.line((54, 1842, W - 54, 1842), fill=GARIS, width=2)
    kanan = catatan_kaki or "Jasa Racik Build DPS"
    rapor._tengah(d, W // 2, 1860, kanan, rapor._font(30, True), EMAS)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue(), {"awal": awal["dps"], "terbaik": terbaik["dps"], "naik": naik}


# ------------------------------------------------------------ 3. /papan (Dashboard Kanban Orderan)

def buat_papan(daftar_profil: list[tuple[str, dict]], catatan_kaki: str = "") -> tuple[bytes, dict] | None:
    """Dashboard visual 3 kolom (Prioritas Kerja | Siap Ditagih | Lunas) dengan progress bar mini."""
    proses, siap, lunas = [], [], []
    for pid, p in daftar_profil:
        if pid == "akun1" and len(daftar_profil) > 1:
            continue
        ok = catatan.baca_ok(pid)
        if not ok:
            continue
        terbaik = max(r["dps"] for r in ok)
        awal = ok[0]["dps"]
        target = int(p.get("target") or 0)
        bayar = str(p.get("bayar") or "").strip().lower()
        sudah_lunas = bayar in ("lunas", "paid", "sudah", "ok")
        tembus = bool(target and terbaik >= target)
        pct = (terbaik / target * 100) if target else 0.0
        item = {
            "nama": str(p.get("nick") or p.get("nama") or pid),
            "job": str(p.get("job") or ""),
            "terbaik": terbaik,
            "awal": awal,
            "target": target,
            "pct": pct,
            "naik": (terbaik - awal) / awal * 100 if awal else 0.0,
            "bayar": str(p.get("bayar") or "belum"),
            "terakhir": ok[-1]["waktu"],
        }
        if sudah_lunas:
            lunas.append(item)
        elif tembus:
            siap.append(item)
        else:
            proses.append(item)

    if not (proses or siap or lunas):
        return None

    # Urutkan: proses = paling dekat target dulu (biar cepat beres!), siap = terbaru dulu, lunas = terbaru dulu
    proses.sort(key=lambda x: -x["pct"])
    siap.sort(key=lambda x: x["terakhir"], reverse=True)
    lunas.sort(key=lambda x: x["terakhir"], reverse=True)

    MAKS = 7
    baris_max = max(len(proses[:MAKS]), len(siap[:MAKS]), len(lunas[:MAKS]), 2)
    W = 1280
    H = 220 + baris_max * 98 + 86
    img = Image.new("RGB", (W, H), BG)
    rapor._gradasi_v(img, 0, 0, W, 128, (22, 34, 68), (13, 19, 38))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 124, W, 128), fill=CYAN)

    d.text((40, 20), "PAPAN ANTREAN ORDERAN DPS", font=rapor._font(22, True), fill=CYAN)
    d.text((40, 50), f"Prioritas Kerja Hari Ini  •  {datetime.now():%d/%m/%Y %H:%M}", font=rapor._font(36, True), fill=PUTIH)

    ringkasan = f"{len(proses)} Proses  •  {len(siap)} Siap Tagih  •  {len(lunas)} Lunas"
    d.text((W - 40 - d.textlength(ringkasan, font=rapor._font(22, True)), 62), ringkasan, font=rapor._font(22, True), fill=EMAS)

    kol_w = (W - 80 - 40) // 3
    y0 = 152
    kol_h = H - y0 - 66
    kolom = [
        ("PRIORITAS KERJA", f"{len(proses)} akun (dekat target)", ORANYE, proses),
        ("SIAP DITAGIH", f"{len(siap)} tembus target", HIJAU, siap),
        ("SELESAI & LUNAS", f"{len(lunas)} selesai", CYAN, lunas),
    ]

    for idx, (judul, sub, col, items) in enumerate(kolom):
        x0 = 40 + idx * (kol_w + 20)
        d.rounded_rectangle((x0, y0, x0 + kol_w, y0 + kol_h), 18, fill=KARTU, outline=GARIS, width=2)
        d.rounded_rectangle((x0 + 24, y0, x0 + kol_w - 24, y0 + 5), 3, fill=col)
        d.text((x0 + 20, y0 + 16), judul, font=rapor._font(21, True), fill=col)
        d.text((x0 + 20, y0 + 44), sub, font=rapor._font(16), fill=ABU)
        d.line((x0 + 18, y0 + 70, x0 + kol_w - 18, y0 + 70), fill=GARIS, width=1)

        if not items:
            rapor._tengah(d, x0 + kol_w // 2, y0 + 120, "(kosong)", rapor._font(20), ABU)
            continue

        for r_i, it in enumerate(items[:MAKS]):
            ry = y0 + 82 + r_i * 96
            d.rounded_rectangle((x0 + 16, ry, x0 + kol_w - 16, ry + 84), 12, fill=KARTU2)
            nm = it["nama"][:17]
            d.text((x0 + 28, ry + 10), nm, font=rapor._font(20, True), fill=PUTIH)
            pct_t = f"{it['pct']:.0f}%" if it["target"] else f"{it['naik']:+.0f}%"
            d.text((x0 + kol_w - 28 - d.textlength(pct_t, font=rapor._font(20, True)), ry + 10),
                   pct_t, font=rapor._font(20, True), fill=col)

            info_s = f"{umum.fmt(it['terbaik'])}" + (f" / {umum.fmt(it['target'])}" if it["target"] else "")
            d.text((x0 + 28, ry + 38), info_s, font=rapor._font(16), fill=ABU)

            # Mini progress bar
            bx0, bx1 = x0 + 28, x0 + kol_w - 28
            d.rounded_rectangle((bx0, ry + 64, bx1, ry + 73), 4, fill=(12, 17, 34))
            ras = min(1.0, it["pct"] / 100.0) if it["target"] else 1.0
            d.rounded_rectangle((bx0, ry + 64, bx0 + max(8, int((bx1 - bx0) * ras)), ry + 73), 4, fill=col)

        if len(items) > MAKS:
            rapor._tengah(d, x0 + kol_w // 2, y0 + kol_h - 30, f"+{len(items) - MAKS} akun lainnya",
                          rapor._font(16, True), ABU)

    # Kaki
    fy = H - 48
    d.line((40, fy, W - 40, fy), fill=GARIS, width=1)
    d.text((40, fy + 14), "Tips: kerjakan kolom Prioritas Kerja paling atas dulu (paling dekat tembus target).",
           font=rapor._font(18), fill=ABU)
    kanan = catatan_kaki or "RO DPS Monitor"
    d.text((W - 40 - d.textlength(kanan, font=rapor._font(18, True)), fy + 14), kanan, font=rapor._font(18, True), fill=EMAS)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue(), {"proses": len(proses), "siap": len(siap), "lunas": len(lunas)}
