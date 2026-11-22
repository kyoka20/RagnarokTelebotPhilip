"""Laporan pemakaian bot untuk developer (/pemakaian): dibaca dari log/bot.log (+ bot.log.1..3).

Tujuannya: dari jauh tahu fitur apa yang Philip pakai, apa yang belum pernah, dan masalah apa yang sering muncul.
Hanya membaca log, tidak mengubah apa pun.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# Perintah utama yang berguna untuk Philip (dicek mana yang belum pernah dipakai).
UTAMA = ["/input", "/daftar", "/lihat", "/pilih", "/pindah", "/rapor", "/arsip", "/hari", "/tagihan",
         "/stat", "/sasaran", "/saran", "/batu", "/db", "/target", "/job", "/status", "/ss"]
ALIAS = {"/list": "/daftar", "/rekam": "/record_train", "/train": "/record_train", "/shutdown": "/matikan"}
SEMUA = set(UTAMA) | {"/help", "/start", "/stop", "/batal", "/record_train", "/stop_train", "/matikan",
                      "/nick", "/profil", "/lihat24"}

_BARIS = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d) \[(\w+)\] (.*)$")


def _baca(folder: Path, sejak: datetime):
    files = [folder / f"bot.log.{i}" for i in (3, 2, 1)] + [folder / "bot.log"]
    for f in files:
        try:
            teks = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for baris in teks.splitlines():
            m = _BARIS.match(baris)
            if not m:
                continue
            try:
                w = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if w >= sejak:
                yield w, m.group(3), m.group(4)


def _rapikan(p: str) -> str | None:
    p = ALIAS.get(p, p)
    if p in SEMUA:
        return p
    m = re.fullmatch(r"(/[a-z_]+?)\d+", p)  # /lihat24
    if m and ALIAS.get(m.group(1), m.group(1)) in SEMUA:
        return ALIAS.get(m.group(1), m.group(1))
    return None


def laporan(folder: Path, hari: int = 7, sekarang: datetime | None = None) -> str:
    sekarang = sekarang or datetime.now()
    sejak = sekarang - timedelta(days=hari)
    pertama = None
    tes, hari_tes, karakter = 0, set(), set()
    perintah, salah_ketik = Counter(), 0
    n = Counter()
    afk = timedelta()
    for w, level, isi in _baca(folder, sejak):
        pertama = pertama or w
        m = re.match(r"\[(.+?)\] DPS [\d.,]+ ", isi)
        if m:
            tes += 1
            hari_tes.add(w.date())
            karakter.add(m.group(1))
            continue
        if isi.startswith("Perintah: "):
            if isi.endswith("[dev]"):
                continue  # perintah dari developer tidak dihitung
            p = _rapikan(isi[10:].split(" ")[0].lower())
            if p:
                perintah[p] += 1
            else:
                salah_ketik += 1
            continue
        for kunci, pola in (("hasil", "Terkirim 'hasil DPS'"), ("rapor", "Terkirim 'rapor'"),
                            ("ringkasan", "Ringkasan harian otomatis dikirim"), ("nyala", "Bot jalan."),
                            ("dobel", "sedang dijalankan di tempat lain"), ("putus", "Koneksi ke Telegram putus"),
                            ("jendela", "Jendela game '"), ("gagal_kirim", "Gagal kirim"),
                            ("ditolak", "Telegram menolak"), ("job_auto", "Job terdeteksi")):
            if pola in isi:
                n[kunci] += 1
        if level == "ERROR":
            n["error"] += 1
        m = re.match(r"AFK selesai: (\d\d:\d\d:\d\d) - (\d\d:\d\d:\d\d)", isi)
        if m:
            a, b = (datetime.strptime(x, "%H:%M:%S") for x in m.groups())
            afk += (b - a) if b >= a else (b - a + timedelta(days=1))

    if pertama is None:
        return "📊 Belum ada log untuk dibaca."
    jam_afk = afk.total_seconds() / 3600
    baris = [f"📊 <b>Pemakaian bot</b> {pertama:%d/%m} – {sekarang:%d/%m} ({(sekarang - pertama).days + 1} hari)",
             f"🎮 Test DPS: <b>{tes}</b> di {len(hari_tes)} hari · {len(karakter)} karakter"
             + (f" · AFK {jam_afk:.1f} jam" if jam_afk >= 0.1 else "")]
    total = sum(perintah.values())
    if total:
        top = ", ".join(f"{p} {c}" for p, c in perintah.most_common(6))
        baris.append(f"⌨️ Perintah Philip ({total}x): {top}" + (f" · salah ketik {salah_ketik}" if salah_ketik else ""))
    else:
        baris.append("⌨️ Philip belum mengetik perintah apa pun.")
    belum = [p for p in UTAMA if not perintah[p]]
    if belum:
        baris.append("💤 Belum pernah dipakai: " + " ".join(belum))
    baris.append(f"🤖 Otomatis terkirim: {n['hasil']} hasil DPS · {n['rapor']} rapor · {n['ringkasan']} ringkasan malam")
    sehat = [f"nyala/restart {n['nyala']}x"]
    for k, nama in (("dobel", "bot dobel (409)"), ("putus", "internet putus"), ("jendela", "jendela game hilang"),
                    ("ditolak", "pesan ditolak Telegram"), ("error", "error")):
        if n[k]:
            sehat.append(f"{nama} {n[k]}x")
    baris.append("🩺 " + " · ".join(sehat))

    saran = []
    if perintah["/job"] >= 5:
        saran.append(f"/job diketik {perintah['/job']}x → tebakan job otomatis sering salah.")
    if n["dobel"]:
        saran.append("Bot sempat jalan di 2 tempat sekaligus (laporan bisa hilang). Pastikan hanya di laptop Philip.")
    if n["ditolak"]:
        saran.append("Ada pesan yang ditolak Telegram → cek /log.")
    if tes >= 10 and not perintah["/rapor"] and not n["rapor"]:
        saran.append("/rapor belum pernah dipakai: gambar sebelum-sesudah siap diteruskan ke pembeli.")
    if tes >= 10 and not perintah["/tagihan"]:
        saran.append("/tagihan belum pernah dipakai: daftar pembeli yang siap ditagih.")
    if perintah["/help"] >= 5:
        saran.append(f"/help dibuka {perintah['/help']}x → Philip mungkin sering lupa perintah.")
    if saran:
        baris.append("\n💡 " + "\n💡 ".join(saran))
    baris.append(f"\n<i>Log hanya menyimpan ±1 minggu terakhir.</i>")
    return "\n".join(baris)
