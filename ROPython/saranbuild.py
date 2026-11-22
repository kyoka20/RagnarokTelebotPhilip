"""Saran build per karakter (/saran nama): hanya hal yang berpengaruh ke angka Damage Challenge.

Sumber data (semua dari layar, tidak menyentuh game):
  • riwayat DPS (data/<profil>/riwayat.csv)
  • stat dari halaman Detailed Stats (data/<profil>/status_log.jsonl)
  • enchant: set + level yang terlihat di halaman Enchant (data/<profil>/enchant.json),
    atau build lengkap per equipment (dengan level tiap batu) kalau ada.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import catatan
import datagame
import umum

SLOT_DPS = ("Weapon", "Accessory", "Headwear", "Backwear")
SET_TERBAIK = {"Weapon": "Swift Attack II", "Accessory": "Swift Attack II", "Headwear": "Frenzy III", "Backwear": "Frenzy III"}
SINGKAT = {"Weapon": "Weapon", "Accessory": "Acc", "Headwear": "Head", "Backwear": "Back"}


# ------------------------------------------------------------ angka efek

def _efek(teks: str) -> dict[str, tuple[float, bool]]:
    """'ATK +10, Elemental DMG% +1%' -> {'ATK': (10, False), 'Elemental DMG%': (1, True)}"""
    hasil = {}
    for bagian in re.split(r",\s*(?=[A-Za-z])", teks or ""):
        m = re.match(r"\s*(.+?)\s*\+\s*([\d.]+)\s*(%?)\s*$", bagian)
        if m:
            hasil[m.group(1)] = (float(m.group(2)), bool(m.group(3)) or m.group(1).endswith("%"))
    return hasil


def efek_set(nama: str, lv: int) -> tuple[dict, bool]:
    """Efek set di level lv. (efek, perkiraan?) - kalau level itu belum tercatat, diperkirakan linear."""
    s = datagame.enchant_lokal().get("set", {}).get(nama, {})
    tabel = {int(k): _efek(v) for k, v in (s.get("level") or {}).items() if _efek(v)}
    if lv <= 0 or not tabel:
        return {}, True
    if lv in tabel:
        return tabel[lv], False
    lvs = sorted(tabel)
    if len(lvs) >= 2:
        a, b = lvs[-2], lvs[-1]
        return {k: (tabel[b][k][0] + (tabel[b][k][0] - tabel[a].get(k, (0, 0))[0]) / (b - a) * (lv - b), tabel[b][k][1])
                for k in tabel[b]}, True
    k0 = lvs[0]
    return {k: (v * lv / k0, p) for k, (v, p) in tabel[k0].items()}, True


def _angka(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v - round(v)) > 1e-6 else str(int(round(v)))


BUKAN_DPS = re.compile(r"^(Max )?(HP|SP|DEF|M\.DEF|P\.DEF|FLEE|CRIT RES|.*Recovery|.*Regen|VIT)\b", re.I)


def _fmt(efek: dict) -> str:
    """Hanya stat yang berpengaruh ke damage (HP/DEF/dll disembunyikan)."""
    return ", ".join(f"{k} +{_angka(v)}{'%' if p else ''}" for k, (v, p) in efek.items()
                     if v > 0 and not BUKAN_DPS.match(k))


def _nama_gem(teks: str) -> str:
    gem = datagame.enchant_lokal().get("gem", {})
    t = teks.strip()
    for n in gem:
        if n.lower() == t.lower() or n.lower() == (t + " gem").lower():
            return n
    for n in gem:
        if n.lower().startswith(t.lower()):
            return n
    return t


def efek_gem(nama: str, naik: int = 1) -> dict:
    g = datagame.enchant_lokal().get("gem", {}).get(nama, {})
    if not g.get("stat") or not g.get("per_level"):
        return {}
    return {g["stat"]: (g["per_level"] * naik, bool(g.get("persen")))}


# ------------------------------------------------------------ build

def build_dari_contoh(d: dict) -> list[dict]:
    """Format contoh di enchant.json: 'Royal Berdysz +16 (Weapon)': 'Swift Attack II: Domineering Lv3, STR Lv5, AGI Lv5 -> Lv3'"""
    hasil = []
    for k, v in d.items():
        m = re.match(r"(.+?)\s*\((.+?)\)\s*$", k)
        if not m:
            continue
        item = {"equip": m.group(1), "slot": m.group(2), "set": None, "level": None, "gem": {}}
        ms = re.match(r"([^:]+):\s*(.+?)(?:->\s*Lv\s*(\d+))?$", v)
        if ms and "TIDAK AKTIF" not in v:
            item["set"] = ms.group(1).strip()
            item["level"] = int(ms.group(3)) if ms.group(3) else None
            for g, lv in re.findall(r"([A-Za-z' ]+?)\s+Lv\s*(\d+)", ms.group(2)):
                item["gem"][_nama_gem(g.strip(" ,"))] = int(lv)
        hasil.append(item)
    return hasil


def _slot_dari_set(nama: str) -> str | None:
    s = datagame.enchant_lokal().get("set", {}).get(nama, {})
    sl = s.get("slot") or []
    return sl[0] if sl else None


def saran_enchant(items: list[dict]) -> list[str]:
    """Daftar prioritas naik level batu (paling murah & paling berpengaruh dulu). Hanya slot DPS."""
    calon, ganti = [], []
    for it in items:
        slot = it.get("slot") or _slot_dari_set(it.get("set") or "")
        if slot not in SLOT_DPS:
            continue
        nama_set, lv = it.get("set"), it.get("level")
        label = f"{it['equip']} ({SINGKAT[slot]})" if it.get("equip") else f"{SINGKAT[slot]}"
        if not nama_set:
            ganti.append(f"{label}: set belum aktif → pasang {SET_TERBAIK[slot]}")
            continue
        if nama_set != SET_TERBAIK[slot] and not nama_set.startswith("Swift Attack (Create"):
            ganti.append(f"{label}: {nama_set} → ganti ke {SET_TERBAIK[slot]} "
                         f"({' + '.join(datagame.enchant_lokal()['set'].get(SET_TERBAIK[slot], {}).get('gem', []))})")
        gem = it.get("gem") or {}
        if gem:
            lv = min(gem.values())
            bawah = [g for g, l in gem.items() if l == lv]
        else:
            bawah = None
        if not lv:
            continue
        sekarang, _ = efek_set(nama_set, lv)
        nanti, kira = efek_set(nama_set, lv + 1)
        tambah = {k: (v - sekarang.get(k, (0, 0))[0], p) for k, (v, p) in nanti.items()}
        for g in bawah or []:
            for k, (v, p) in efek_gem(g).items():
                tambah[k] = (tambah.get(k, (0, p))[0] + v, p)
        biaya = len(bawah) if bawah else 3
        apa = (" + ".join(f"{g.replace(' Gem', '')} Lv{lv}→{lv + 1}" for g in bawah) if bawah
               else f"batu terendah Lv{lv}→{lv + 1}")
        calon.append((biaya, lv, f"{label} {nama_set} Lv{lv}: naikkan {apa} ({biaya} batu)"
                                 + (f"\n      → {'≈' if kira else ''}{_fmt(tambah)}" if _fmt(tambah) else "")))
    calon.sort(key=lambda x: (x[0], x[1]))
    baris = []
    if ganti:
        baris += ["🔁 " + g for g in ganti]
    for i, (_, _, t) in enumerate(calon[:5], 1):
        baris.append(f"{i}. {t}")
    return baris


# ------------------------------------------------------------ simpan enchant per karakter

def _file_enchant(pid: str):
    return catatan.folder_profil(pid) / "enchant.json"


def muat_enchant(pid: str) -> dict:
    try:
        return json.loads(_file_enchant(pid).read_text(encoding="utf-8"))
    except Exception:
        return {}


def catat_set_terlihat(pid: str, nama_set: str, level: int) -> None:
    """Dipanggil bot saat halaman Enchant karakter ini terbaca: simpan set + level yang terlihat."""
    d = muat_enchant(pid)
    t = d.setdefault("terlihat", {})
    lv = set(t.get(nama_set, {}).get("level", []))
    lv.add(int(level))
    t[nama_set] = {"level": sorted(lv), "waktu": datetime.now().strftime("%Y-%m-%d %H:%M")}
    _file_enchant(pid).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def build_karakter(pid: str) -> tuple[list[dict], str]:
    """(items, sumber). Build lengkap kalau ada, kalau tidak dari set yang terlihat."""
    d = muat_enchant(pid)
    if d.get("build"):
        return build_dari_contoh(d["build"]), "build per equipment"
    items = []
    for nama, info in (d.get("terlihat") or {}).items():
        for lv in info.get("level", []):
            items.append({"equip": None, "slot": _slot_dari_set(nama), "set": nama, "level": lv, "gem": {}})
    return items, ("set terlihat di halaman Enchant" if items else "")


# ------------------------------------------------------------ saran lengkap

def _ringkas_dps(pid: str, target: int | None) -> list[str]:
    ok = catatan.baca_ok(pid)
    if not ok:
        return ["⚔️ Belum ada hasil DPS."]
    rekor = max(ok, key=lambda r: r["dps"])
    akhir = ok[-1]
    baris = [f"⚔️ Rekor {umum.fmt(rekor['dps'])} ({rekor['waktu']:%d/%m %H:%M}) | terakhir {umum.fmt(akhir['dps'])} | {len(ok)} test"]
    if target:
        if rekor["dps"] >= target:
            baris.append(f"🎯 Target {umum.fmt(target)} SUDAH tercapai")
        else:
            baris.append(f"🎯 Target {umum.fmt(target)}: kurang {umum.fmt(target - rekor['dps'])} "
                         f"(+{(target / rekor['dps'] - 1) * 100:.1f}% dari rekor)")
    if len(ok) >= 6:
        a = sum(r["dps"] for r in ok[-3:]) / 3
        b = sum(r["dps"] for r in ok[-6:-3]) / 3
        arah = (a / b - 1) * 100
        if abs(arah) >= 2:
            baris.append(f"📈 3 test terakhir {'naik' if arah > 0 else 'turun'} {abs(arah):.1f}% dibanding 3 sebelumnya")
    return baris


def _nama_stat_awam(label: str) -> str:
    """Ubah label teknis seperti 'DMG vs Medium +5%' -> bahasa singkat yang langsung paham."""
    s = re.sub(r"\s*\+\d+(?:\.\d+)?%?", "", label).strip()
    peta = {
        "DMG vs Human": "Kartu/Stat vs Human",
        "DMG vs Medium": "Kartu/Stat vs Medium",
        "DMG vs Neutral": "Kartu/Stat vs Neutral",
        "P.DMG Bonus": "P.DMG%",
        "M.DMG Bonus": "M.DMG%",
        "Elemental DMG": "Elemental DMG%",
        "Skill DMG": "Skill DMG%",
        "CRIT DMG": "CRIT DMG%",
        "Ignore P.DEF": "Ignore DEF",
        "Ignore M.DEF": "Ignore M.DEF",
        "Final DMG": "Final DMG%",
    }
    return peta.get(s, s)


def _kartu_rekomendasi(st: dict, sasaran_test: dict) -> list[str]:
    """Cari 1-2 saran kartu paling konkret untuk sasaran dummy."""
    import sasaran
    kartu = sasaran.kartu_cocok(sasaran_test)
    saran_k = []
    for nama_stat, kata in (
        (f"DMG vs {sasaran_test['ukuran']}%", sasaran_test["ukuran"]),
        (f"DMG vs {sasaran_test['elemen']}%", sasaran_test["elemen"]),
        (f"DMG vs {sasaran_test['ras']}%", sasaran_test["ras"]),
    ):
        val = sasaran._f(st.get(nama_stat, 0))
        if kata == "Human":
            val += sasaran._f(st.get("DMG vs Demi-Human%", 0))
        if val == 0:
            calon = [k for k in kartu if kata.lower() in k[2].lower() or (kata == "Human" and "demi-human" in k[2].lower())][:1]
            if calon:
                n, slot, _ = calon[0]
                saran_k.append(f"<b>{n}</b> ({slot}, bonus vs {kata})")
    return saran_k


def saran(pid: str, profil: dict, sasaran_test: dict) -> list[str]:
    import bacabuild
    import rumus
    import sasaran
    import statistik

    nama = profil.get("nick") or profil.get("nama") or pid
    job = profil.get("job") or ""
    target = int(profil.get("target") or 0)
    ok = catatan.baca_ok(pid)
    log = bacabuild.baca_log(pid)
    stat_log = statistik.baca_log(pid)
    sumber_skill = stat_log[-1].get("sumber") if stat_log else None
    items, sumber_ench = build_karakter(pid)

    st = {}
    for _, s in log:
        st.update(s)

    prio, warn, pb = ([], [], {"magic": False, "ranged": False})
    if st:
        prio, warn, pb = rumus.prioritas_stat(st, sasaran_test, job, sumber_skill)
    tipe = "Magic" if pb["magic"] else ("Fisik Ranged" if pb["ranged"] else "Fisik Melee")

    # ---------------- Header singkat ----------------
    baris = [f"🧭 <b>Saran Build: {nama}</b>" + (f" ({job})" if job else (f" [{tipe}]" if st else ""))]
    tembus = False
    if ok:
        rekor = max(ok, key=lambda r: r["dps"])
        akhir = ok[-1]
        if target and rekor["dps"] >= target:
            tembus = True
            baris.append(f"⚔️ Rekor <b>{umum.fmt(rekor['dps'])}</b> — 🎯 <b>TARGET {umum.fmt(target)} SUDAH TEMBUS!</b>")
        elif target:
            kurang = target - rekor["dps"]
            pct_k = (target / rekor["dps"] - 1) * 100
            baris.append(f"⚔️ Rekor <b>{umum.fmt(rekor['dps'])}</b> / Target {umum.fmt(target)} (kurang {umum.fmt(kurang)} / +{pct_k:.1f}%)")
        else:
            baris.append(f"⚔️ Rekor <b>{umum.fmt(rekor['dps'])}</b> | terakhir {umum.fmt(akhir['dps'])} ({len(ok)} test)")
    else:
        baris.append("⚔️ Belum ada hasil test DPS.")

    # ---------------- KESIMPULAN: LAKUKAN INI DULU ----------------
    langkah: list[str] = []
    if tembus:
        langkah.append("Target sudah tercapai! Tinggal kirim <code>/rapor</code> atau <code>/gif</code> ke pembeli.")
    else:
        # 1) Kartu / stat terbuang atau masih 0%
        if st:
            _, buang = sasaran.stat_sasaran(sasaran_test)
            terbuang = [(n, st[n]) for n in buang if sasaran._f(st.get(n, 0)) > 0]
            total_buang = sum(sasaran._f(v) for _, v in terbuang)
            kartu_saran = _kartu_rekomendasi(st, sasaran_test)
            if total_buang >= 5:
                langkah.append(f"<b>Ganti kartu/equip yg salah sasaran</b> (ada {total_buang:.0f}% bonus ke ras/elemen lain yg tidak ngefek di Dummy).")
            if kartu_saran:
                langkah.append("<b>Pasang kartu yg masih kosong:</b> " + " atau ".join(kartu_saran[:2]) + " — efeknya langsung terasa di Dummy.")
            # 2) Stat paling ngebut buat dinaikkan
            if prio:
                top_stat = [_nama_stat_awam(p["label"]) for p in prio[:3]]
                # Hilangkan duplikat
                top_unik = list(dict.fromkeys(top_stat))
                langkah.append("<b>Fokus naikkan stat ini dulu:</b> " + ", ".join(top_unik) + ".")
            # 3) Jangan buang stat yang sudah mentok cap
            for w in warn[:1]:
                bersih = w.lstrip("⚠️✅ℹ️ ").strip()
                langkah.append(f"<b>Jangan tambah lagi:</b> {bersih}")
        else:
            langkah.append("Buka halaman <b>Character Info → Detailed Stats</b> di game sekali (scroll sampai bawah), supaya bot tahu stat apa yang kurang.")

        # 4) Batu Enchant paling murah dinaikkan
        e_list = saran_enchant(items) if items else []
        if e_list:
            pertama = e_list[0].replace("\n      ", " ").lstrip("12345. ")
            langkah.append(f"<b>Upgrade batu Enchant termurah:</b> {pertama}")
        elif not items:
            langkah.append("Buka halaman <b>Enchant</b> di game (klik Weapon/Acc/Head/Back) biar bot bisa urutkan batu termurah.")

        # 5) Skill utama dari Statistics (kalau ada)
        if sumber_skill:
            utama = sumber_skill[0]
            langkah.append(f"Damage terbesar dari <b>{utama['nama']} ({utama['persen']:g}%)</b> — prioritaskan kartu/rune/affix yang memperkuat skill ini.")

    baris += ["", "🎯 <b>KESIMPULAN — LAKUKAN INI DULU:</b>"]
    for i, l in enumerate(langkah[:4], 1):
        baris.append(f"{i}. {l}")

    # ---------------- Detail Singkat (opsional, biar tetap informatif) ----------------
    detail: list[str] = []
    if st:
        pakai, _ = sasaran.stat_sasaran(sasaran_test)
        ada = [f"{n.replace('DMG vs ', 'vs ')} {st[n]}" for n in pakai if n in st and sasaran._f(st[n]) > 0]
        if ada:
            detail.append("✅ Bonus aktif di Dummy: " + ", ".join(ada))
        if prio:
            detail.append("📈 Efek tiap +5% stat: " + " · ".join(f"{p['singkat']} (+{p['naik_pct']:.1f}%)" for p in prio[:3]))
    if items:
        e_list = saran_enchant(items)
        if len(e_list) > 1:
            detail.append("💎 Urutan batu lain: " + " | ".join(x.splitlines()[0].lstrip("12345. ") for x in e_list[1:3]))
        if pb["magic"]:
            detail.append("ℹ️ Karakter Magic: pakai gem/set M.ATK & M.DMG.")

    if detail:
        baris += ["", "📋 <b>Catatan Singkat:</b>"] + detail

    baris.append("\n💡 Mau hitung efek sebelum ganti build? Ketik <code>/sim +10% pdmg</code> (atau <code>/sim +300 matk</code>).")
    return baris
