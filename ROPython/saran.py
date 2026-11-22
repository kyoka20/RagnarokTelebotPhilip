"""Saran otomatis singkat di laporan DPS (Telegram).

Hanya memakai data yang PASTI benar: angka hasil test karakter ini sendiri
(DPS, Total DMG, Rekor). Belum memakai isi equip/kartu/skill, karena build yang
sedang dipakai belum terbaca dari layar.

Isinya:
- Apakah naik/turun ini NYATA atau masih dalam batas acak (crit dll) karakter ini.
- Rekor di layar lebih tinggi dari hasil sekarang -> build lama pernah lebih kuat.
- Sudah lama tidak ada kenaikan nyata -> coba perubahan yang lebih besar.
- Lompatan sangat besar -> cek karakter / buff / equip.
"""
from __future__ import annotations

import statistics as st
from datetime import datetime, timedelta

import umum

ACAK_DEFAULT = 0.01   # 1%: kalau data karakter ini belum cukup untuk mengukur batas acak
ACUAN_JAM = 6         # test lebih lama dari ini dianggap build lain, tidak dipakai pembanding


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%".replace(".", ",")


def _pct_mutlak(x: float) -> str:
    return f"{abs(x) * 100:.1f}%".replace(".", ",")


def _jt(n: float) -> str:
    return f"{n / 1e6:.2f} jt".replace(".", ",")


def batas_acak(riwayat: list[dict]) -> tuple[float, bool]:
    """Seberapa besar DPS naik-turun sendiri walau build sama (dalam pecahan, mis. 0.009).
    Diukur dari selisih test berturut-turut (median, jadi lompatan karena ganti equip tidak ikut).
    Hasil: (batas, sudah_diukur?)."""
    beda = []
    for a, b in zip(riwayat, riwayat[1:]):
        if (b["waktu"] - a["waktu"]) <= timedelta(hours=ACUAN_JAM) and a["dps"]:
            x = abs(b["dps"] - a["dps"]) / a["dps"]
            if x <= 0.08:  # beda lebih dari 8% = ganti build, bukan acak
                beda.append(x)
    if len(beda) < 5:
        return ACAK_DEFAULT, False
    sigma = 1.4826 * st.median(beda) / 2 ** 0.5
    return min(max(sigma, 0.004), 0.03), True


def _acuan(dekat: list[dict]) -> float | None:
    """Rata-rata sampai 3 test terakhir yang masih satu 'tingkat build' dengan test terakhir
    (berhenti kalau ketemu lompatan lebih dari 8%)."""
    if not dekat:
        return None
    akhir = dekat[-1]["dps"]
    ambil = []
    for d in reversed(dekat):
        if abs(d["dps"] - akhir) / akhir > 0.08 or len(ambil) == 3:
            break
        ambil.append(d["dps"])
    return st.mean(ambil)


def buat(riwayat: list[dict], dps: int, total: int | None, rekor: int | None,
         waktu: datetime | None = None, target: int = 0, boleh_jeda: bool = True) -> list[str]:
    """riwayat = hasil test karakter ini SEBELUM test baru (urut lama -> baru).
    boleh_jeda = boleh menampilkan saran '⏳ lama tidak naik' (dibatasi pemanggil, mis. 30 menit sekali).
    Hasil: 0-2 baris saran (teks HTML aman, tanpa input dari luar)."""
    waktu = waktu or datetime.now()
    sigma, diukur = batas_acak(riwayat)
    batas = 2 * sigma
    baris: list[str] = []

    dekat = [d for d in riwayat if waktu - d["waktu"] <= timedelta(hours=ACUAN_JAM)]
    acuan = _acuan(dekat)
    ubah = (dps - acuan) / acuan if acuan else None

    # 1) Lompatan sangat besar: hampir pasti bukan keberuntungan.
    if ubah is not None and ubah <= -0.15:
        baris.append(f"⚠️ Anjlok {_pct_mutlak(ubah)} dari test sebelumnya. Cek: karakter benar? "
                     "Buff/makanan aktif? Equip & kartu lengkap?")
    elif ubah is not None and ubah >= 0.15:
        baris.append(f"🚀 Lompat {_pct(ubah)} dari test sebelumnya. Perubahan terakhir sangat berpengaruh, catat & pertahankan.")

    # 2) Rekor di layar = karakter ini pernah lebih kuat.
    if rekor and total and dps and total < rekor:
        dps_rekor = rekor / (total / dps)
        kurang = (dps_rekor - dps) / dps_rekor
        # Rekor = hasil terbaik dari banyak test, wajar sedikit di atas rata-rata. Baru disebut kalau jauh.
        if kurang > max(4 * sigma, 0.03) and not (ubah is not None and abs(ubah) >= 0.15):
            baris.append(f"🏆 Rekor karakter ini setara ±{_jt(dps_rekor)} DPS, sekarang {_pct_mutlak(kurang)} di bawahnya. "
                         "Build yang dulu lebih kuat, bandingkan.")

    # 3) Naik / turun nyata atau masih acak.
    if ubah is not None and abs(ubah) < 0.15 and len(baris) < 2:
        ket_acak = ("batas acak" if diukur else "batas acak kira-kira") + f" ±{_pct_mutlak(batas)}"
        if ubah >= batas:
            baris.append(f"✅ Naik nyata {_pct(ubah)} ({ket_acak}). Perubahan terakhir berhasil, pertahankan.")
        elif ubah <= -batas:
            baris.append(f"❌ Turun nyata {_pct(ubah)} ({ket_acak}). Perubahan terakhir merugikan, kembalikan.")
        else:
            baris.append(f"↔️ {_pct(ubah)} masih dalam {ket_acak}, belum pasti. Ulangi 1-2x sebelum memutuskan.")
    elif ubah is None and not baris:
        baris.append("💡 Test pertama. Ulangi 2x tanpa ganti apa pun dulu, supaya batas acak DPS karakter ini terukur.")

    # 4) Lama tidak ada kenaikan nyata: rata-rata 1 jam terakhir vs 1 jam sebelumnya.
    naik_nyata = ubah is not None and ubah >= batas
    if len(baris) < 2 and dekat and boleh_jeda and not naik_nyata:
        semua = dekat + [{"waktu": waktu, "dps": dps}]
        sejam = [d["dps"] for d in semua if waktu - d["waktu"] <= timedelta(minutes=60)]
        lalu = [d["dps"] for d in semua if timedelta(minutes=60) < waktu - d["waktu"] <= timedelta(minutes=120)]
        if len(sejam) >= 6 and len(lalu) >= 3:
            beda = (st.mean(sejam) - st.mean(lalu)) / st.mean(lalu)
            perlu = 2 * sigma * (1 / len(sejam) + 1 / len(lalu)) ** 0.5
            if beda < perlu:
                baris.append(f"⏳ {len(sejam)} test 1 jam terakhir, rata-rata {_pct(beda)} dari jam sebelumnya "
                             "(belum naik nyata). Coba perubahan yang lebih besar (kartu, refine, skill).")

    # 5) Target tinggal sedikit.
    if len(baris) < 2 and target and dps < target and (target - dps) / dps <= batas:
        baris.append(f"🎯 Tinggal {_pct_mutlak((target - dps) / dps)} ke target, masih dalam batas acak: ulangi test bisa tembus.")
    return baris[:2]


def teks(baris: list[str]) -> str:
    return "\n".join(["💡 <b>Saran</b>"] + baris) if baris else ""


if __name__ == "__main__":  # uji cepat: python saran.py <profil>
    import sys
    import catatan
    umum.siapkan_konsol()
    pid = sys.argv[1] if len(sys.argv) > 1 else "oniiichann"
    data = catatan.baca_ok(pid)
    jeda_terakhir = None
    for i, d in enumerate(data):
        print(f"{d['waktu']:%d/%m %H:%M} {umum.fmt(d['dps'])}")
        boleh = jeda_terakhir is None or d["waktu"] - jeda_terakhir >= timedelta(minutes=30)
        for b in buat(data[:i], d["dps"], d["total"], d["rekor"], d["waktu"], 3000000, boleh):
            print("    " + b)
            if b.startswith("⏳"):
                jeda_terakhir = d["waktu"]
