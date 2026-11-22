"""Sasaran Damage Challenge: stat & kartu apa yang TERPAKAI saat test, mana yang TERBUANG.

Sasaran diatur di config.json -> "sasaran_test" (default: Damage Test Dummy Humanoid/Medium/Neutral,
dipastikan pemilik 21/11/2026). Data kartu dari database roworlddb.
"""
from __future__ import annotations

import re

import datagame

RAS = ["Human", "Brute", "Demon", "Undead Race", "Formless", "Fish", "Angel", "Insect", "Mech", "Plant", "Dragon"]
UKURAN = ["Small", "Medium", "Large"]
ELEMEN = ["Neutral", "Water", "Earth", "Fire", "Wind", "Poison", "Holy", "Shadow", "Ghost", "Undead"]

DEFAULT = {"nama": "Damage Test Dummy (Humanoid, Medium)", "ras": "Human", "ukuran": "Medium", "elemen": "Neutral"}


def _f(v) -> float:
    try:
        return float(str(v).rstrip("%").replace(",", ""))
    except ValueError:
        return 0.0


def stat_sasaran(s: dict) -> tuple[list[str], list[str]]:
    """(nama stat yang terpakai melawan sasaran, nama stat bonus-ras/ukuran/elemen yang terbuang)."""
    pakai = [f"DMG vs {s['ras']}%", f"DMG vs {s['ukuran']}%", f"DMG vs {s['elemen']}%"]
    if s["ras"] == "Human":
        pakai.append("DMG vs Demi-Human%")
    buang = [f"DMG vs {r}%" for r in RAS if r != s["ras"]] + [f"DMG vs {u}%" for u in UKURAN if u != s["ukuran"]] \
        + [f"DMG vs {e}%" for e in ELEMEN if e != s["elemen"]]
    return pakai, buang


def kartu_cocok(s: dict) -> list[tuple[str, str, str]]:
    """Kartu (nama, slot, efek) yang menambah damage ke ras/ukuran/elemen sasaran."""
    ras = "Demi-?Human|Human" if s["ras"] == "Human" else re.escape(s["ras"])
    pola = re.compile(rf"^DMG vs ({ras}|{re.escape(s['ukuran'])}|{re.escape(s['elemen'])})%", re.I)
    hasil = []
    for c in datagame._muat("kartu.json")["cards"]:
        efek = [e for e in c.get("effect_lines") or [] if pola.search(e)]
        if efek:
            hasil.append((c["name"], c.get("card_type_name") or "?", efek[0]))

    def kuat(x):  # angka maksimum di efek, mis. "+12%~20%" -> 20
        angka = [float(a) for a in re.findall(r"(\d+(?:\.\d+)?)%", x[2])]
        return -(max(angka) if angka else 0)
    return sorted(hasil, key=kuat)


def analisis(status: dict, s: dict) -> list[str]:
    """Baris saran singkat dari stat karakter terhadap sasaran test."""
    pakai, buang = stat_sasaran(s)
    baris = []
    ada = [(n, status[n]) for n in pakai if n in status and _f(status[n]) > 0]
    if ada:
        baris.append("✅ Terpakai di test: " + ", ".join(f"{n} {v}" for n, v in ada))
    terbuang = [(n, status[n]) for n in buang if _f(status.get(n, 0)) > 0]
    total = sum(_f(v) for _, v in terbuang)
    if terbuang:
        teratas = sorted(terbuang, key=lambda x: -_f(x[1]))[:4]
        baris.append(f"⚠️ Tidak terpakai di test (total {total:.1f}%): "
                     + ", ".join(f"{n.replace('DMG vs ', 'vs ')} {v}" for n, v in teratas)
                     + (" ..." if len(terbuang) > 4 else ""))
    kartu = kartu_cocok(s)
    for nama_stat, kata in ((f"DMG vs {s['ukuran']}%", s["ukuran"]), (f"DMG vs {s['elemen']}%", s["elemen"])):
        if _f(status.get(nama_stat, 0)) == 0:
            calon = [k for k in kartu if kata.lower() in k[2].lower()][:2]
            if calon:
                baris.append(f"💡 Bonus vs {kata} tidak terlihat di stat (kemungkinan 0). Kartu: "
                             + "; ".join(f"{n} ({slot}) {e.split(' / ')[0]}" for n, slot, e in calon))
    return baris


_ROMAWI = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}


def _tingkat(nama: str) -> int:
    return _ROMAWI.get(nama.split()[-1], 0)


def saran_batu(slot_cari: str = "") -> list[str]:
    """Saran set enchant (batu) per slot untuk DPS, dari database enchant (+ hasil belajar otomatis)."""
    db = datagame.enchant_lokal()
    sets = db.get("set", {})
    per_slot: dict[str, list[str]] = {}
    for nama, s in sets.items():
        for sl in s.get("slot") or []:
            per_slot.setdefault(sl, []).append(nama)
    urutan = ["Weapon", "Accessory", "Headwear", "Backwear", "Facewear", "Mouthwear", "Armor", "Cape", "Shoes", "Off-Hand"]
    if slot_cari:
        cocok = datagame.skor_nama if hasattr(datagame, "skor_nama") else None
        urutan = [sl for sl in urutan if slot_cari.lower() in sl.lower()] or \
                 [max(urutan, key=lambda sl: cocok(slot_cari, sl) if cocok else 0)]
    baris = ["💎 <b>Saran batu enchant per slot (untuk DPS)</b>"]
    for sl in urutan:
        daftar = sorted(per_slot.get(sl, []), key=lambda n: (-_tingkat(n), n))
        dps = [n for n in daftar if sets[n].get("fokus") == "DPS"]
        if dps:
            utama = dps[0]
            s = sets[utama]
            lv = s.get("level", {})
            efek = ""
            if lv:
                k = max(lv, key=int)
                efek = f"\n      set Lv.{k}: {lv[k]}"
            cadangan = f"\n      cadangan: {', '.join(dps[1:3])}" if len(dps) > 1 else ""
            baris.append(f"⚔️ <b>{sl}</b>: {utama} = {' + '.join(s.get('gem', []))}{efek}{cadangan}")
        elif daftar:
            baris.append(f"🛡 <b>{sl}</b>: set bertahan ({', '.join(daftar[:3])}). Tidak menambah angka test; "
                         "untuk DPS cukup isi batu yang ada, jangan habiskan bahan di sini.")
    baris += ["", "📌 Aturan:",
              "• Level set = level batu TERENDAH di set itu → naikkan batu yang paling rendah dulu.",
              "• Set hanya aktif kalau 3 batunya lengkap (lihat tulisan Active di game).",
              "• STR/AGI: pilih stat utama job (cek /stat sebelum & sesudah test).",
              "🧠 Efek set yang belum tercatat akan terisi sendiri saat Anda membuka halaman Enchant."]
    return baris


def _teks_def(s: dict) -> str | None:
    try:
        import monster
        return monster.teks_stat(s["nama"])
    except Exception:
        return None


def teks_sasaran(s: dict) -> list[str]:
    pakai, _ = stat_sasaran(s)
    baris = [f"🎯 Sasaran test: {s['nama']}", f"Ras {s['ras']} | Ukuran {s['ukuran']} | Elemen {s['elemen']}",
             *([d] if (d := _teks_def(s)) else []),
             "Stat bonus yang terpakai: " + ", ".join(pakai[:3]),
             "Bonus vs ras/ukuran/elemen LAIN tidak berpengaruh ke angka test.", "", "Kartu yang menambah damage ke sasaran ini:"]
    for n, slot, e in kartu_cocok(s):
        baris.append(f"• {n} ({slot}): {e}")
    return baris
