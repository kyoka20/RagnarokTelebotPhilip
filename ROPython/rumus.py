"""Mesin simulasi & kalkulasi DPS Ragnarok: The New World (RTNW).

Tujuan: membantu Philip memilih upgrade stat/kartu/equip/enchant yang paling besar
kenaikan DPS-nya untuk klien, serta mensimulasikan perubahan build (/sim).

Catatan penting (lihat dokumen/peta/rumus-damage.md):
- Rumus akhir damage dihitung di server dan tidak dipublikasikan.
- Model ini memakai struktur multi-bucket standar RTNW/RO yang terverifikasi
  (ATK/M.ATK, PDMG/MDMG, Skill/Normal, Elemental, Race/Size/Ele, CRIT, DEF/Ignore DEF,
  Final DMG, Attack Frequency cap 7.0, Variable Cast Time cap -100%).
- Semakin banyak data test_stat.jsonl & statistik.jsonl terkumpul, fungsi `kalibrasi()`
  bisa mengecek akurasi prediksi terhadap hasil nyata di server.
"""
from __future__ import annotations

import json
import re
from typing import Any

import catatan
import sasaran as mod_sasaran
import umum

# Job magic & ranged (huruf kecil, cocok sebagian nama job)
JOB_MAGIC = ("wizard", "mage", "sage", "professor", "sorcerer", "warlock",
             "priest", "acolyte", "bishop", "chronomancer")
JOB_RANGED = ("sniper", "hunter", "archer", "ranger", "clown", "gypsy",
              "bard", "dancer", "gunslinger", "rebellion", "minstrel", "wanderer")
JOB_AUTO = ("sniper", "hunter", "ranger", "assassin", "gunslinger", "knight", "lord knight")

ELEMEN_DAFTAR = ("Neutral", "Water", "Earth", "Fire", "Wind", "Poison", "Holy", "Shadow", "Ghost", "Undead")
CAP_FREQ = 7.0
CAP_VCT = -100.0


def _f(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").rstrip("%")
    try:
        return float(s)
    except ValueError:
        return default


def _def_sasaran(s: dict) -> tuple[float, float]:
    """(DEF, M.DEF) sasaran test dari monster.json, fallback Dummy (100, 50)."""
    try:
        import monster
        m = monster.cari(s.get("nama", "")) or monster.cari("DMG Test Dummy")
        if m:
            return float(m.get("def") or 100), float(m.get("mdef") or 50)
    except Exception:
        pass
    return 100.0, 50.0


def profil_build(stat: dict[str, Any], job: str = "", sumber_skill: list[dict] | None = None) -> dict[str, Any]:
    """Deteksi otomatis tipe build karakter: magic/fisik, ranged/melee, porsi_skill, elemen_utama."""
    j = (job or "").lower()
    atk = _f(stat.get("ATK"))
    matk = _f(stat.get("M.ATK"))

    is_magic = any(k in j for k in JOB_MAGIC) or (matk > 0 and matk > atk * 1.35)
    is_ranged = (not is_magic) and (
        any(k in j for k in JOB_RANGED)
        or _f(stat.get("Ranged PDMG%")) > _f(stat.get("Melee PDMG%"))
    )

    # Porsi skill vs basic/normal attack
    porsi_skill = 0.95 if is_magic else (0.50 if any(k in j for k in JOB_AUTO) else 0.85)
    skill_teratas = None
    if sumber_skill:
        total_p = sum(float(r.get("persen") or 0) for r in sumber_skill)
        if total_p > 10:
            normal_p = sum(float(r.get("persen") or 0) for r in sumber_skill
                           if any(w in (r.get("nama") or "").lower() for w in ("basic", "normal", "auto")))
            porsi_skill = max(0.05, min(0.98, 1.0 - normal_p / total_p))
            skill_teratas = sumber_skill[0].get("nama")

    # Elemen utama: cari dari stat elemen > 0 yang terbesar, default Neutral
    ele_utama = "Neutral"
    terbesar = 0.0
    for e in ELEMEN_DAFTAR:
        v = _f(stat.get(f"{e} DMG%"))
        if v > terbesar:
            terbesar, ele_utama = v, e

    return {
        "magic": is_magic,
        "ranged": is_ranged,
        "porsi_skill": round(porsi_skill, 2),
        "elemen": ele_utama,
        "skill_teratas": skill_teratas,
    }


def hitung_komponen(stat: dict[str, Any], s_test: dict, pb: dict[str, Any]) -> dict[str, float]:
    """Hitung tiap pengali bucket DPS + skor gabungan (unit relatif)."""
    magic = pb["magic"]
    ranged = pb["ranged"]
    porsi_skill = pb["porsi_skill"]
    ele_utama = pb["elemen"]

    base_atk = max(100.0, _f(stat.get("M.ATK" if magic else "ATK"), 1000.0))

    # Bonus damage fisik / magic + jarak
    dmg_bonus = _f(stat.get("MDMG Bonus%" if magic else "PDMG Bonus%"))
    if magic:
        jarak_bonus = max(_f(stat.get("Ranged MDMG%")), _f(stat.get("Melee MDMG%")))
    else:
        jarak_bonus = _f(stat.get("Ranged PDMG%" if ranged else "Melee PDMG%"))
    m_dmg = 1.0 + (dmg_bonus + jarak_bonus) / 100.0

    # Skill vs Normal Attack
    m_skill_part = 1.0 + _f(stat.get("Skill DMG%")) / 100.0
    m_norm_part = 1.0 + _f(stat.get("Normal Attack DMG%")) / 100.0

    # Speed factor (memengaruhi porsi Normal Attack; cap 7.0/detik)
    freq = _f(stat.get("Attack Frequency"), 0.0)
    m_freq = min(CAP_FREQ, freq) if freq > 0 else 2.0
    # Komponen skill vs normal yang sudah ditimbang kecepatan
    m_style = porsi_skill * m_skill_part + (1.0 - porsi_skill) * m_norm_part * (m_freq / 2.0)

    # Elemental DMG% + elemen spesifik
    m_ele_atk = 1.0 + (_f(stat.get("Elemental DMG%")) + _f(stat.get(f"{ele_utama} DMG%"))) / 100.0

    # Target modifiers (Race, Size, Element sasaran)
    ras = s_test.get("ras", "Human")
    vs_ras = _f(stat.get(f"DMG vs {ras}%"))
    if ras == "Human":
        vs_ras += _f(stat.get("DMG vs Demi-Human%"))
    vs_ukuran = _f(stat.get(f"DMG vs {s_test.get('ukuran', 'Medium')}%"))
    vs_ele = _f(stat.get(f"DMG vs {s_test.get('elemen', 'Neutral')}%"))
    m_target = (1.0 + vs_ras / 100.0) * (1.0 + vs_ukuran / 100.0) * (1.0 + vs_ele / 100.0)

    # DEF mitigation
    def_p, def_m = _def_sasaran(s_test)
    def_s = def_m if magic else def_p
    ign_flat = _f(stat.get("Ignore M.DEF" if magic else "Ignore P.DEF"))
    ign_pct = _f(stat.get("Ignore M.DEF%" if magic else "Ignore P.DEF%"))
    def_eff = max(0.0, def_s * max(0.0, 1.0 - ign_pct / 100.0) - ign_flat)
    m_def = 400.0 / (400.0 + def_eff)

    # CRIT factor (untuk magic hanya aktif jika ada stat crit signifikan)
    crit_val = _f(stat.get("CRIT"))
    crit_dmg = _f(stat.get("CRIT DMG%"))
    if magic and crit_val < 20 and crit_dmg <= 0:
        m_crit = 1.0
    else:
        crit_rate = min(1.0, max(0.0, crit_val / 100.0))
        m_crit = 1.0 + crit_rate * (0.5 + crit_dmg / 100.0)

    # Final DMG%
    final_all = _f(stat.get("Final DMG")) + _f(stat.get("Final MDMG" if magic else "Final PDMG"))
    m_final = 1.0 + final_all / 100.0

    skor = base_atk * m_dmg * m_style * m_ele_atk * m_target * m_def * m_crit * m_final
    return {
        "skor": skor,
        "base_atk": base_atk,
        "m_dmg": m_dmg,
        "m_style": m_style,
        "m_ele_atk": m_ele_atk,
        "m_target": m_target,
        "m_def": m_def,
        "def_eff": def_eff,
        "m_crit": m_crit,
        "m_final": m_final,
    }


def terapkan_delta(stat: dict[str, Any], delta: dict[str, float], pb: dict[str, Any]) -> dict[str, Any]:
    """Buat salinan stat setelah ditambah `delta` (termasuk konversi ATK%/M.ATK% ke ATK/M.ATK)."""
    baru = dict(stat)
    magic = pb["magic"]
    for k, dv in delta.items():
        if k in ("ATK%", "M.ATK%"):
            k_flat = "M.ATK" if k == "M.ATK%" else "ATK"
            pct_lama = _f(baru.get(k), 0.0)
            flat_lama = _f(baru.get(k_flat), 1000.0)
            baru[k] = f"{pct_lama + dv:g}%"
            # ATK tampil di Detailed Stats sudah memuat ATK% lama -> hitung rasio baru
            rasio = (100.0 + pct_lama + dv) / max(1.0, 100.0 + pct_lama)
            baru[k_flat] = f"{flat_lama * rasio:.1f}"
        elif k == "Attack Frequency":
            baru[k] = f"{min(CAP_FREQ, max(0.1, _f(baru.get(k), 2.0) + dv)):.2f}"
        else:
            lama = _f(baru.get(k), 0.0)
            persen = k.endswith("%") or str(stat.get(k, "")).endswith("%")
            baru[k] = f"{lama + dv:g}{'%' if persen else ''}"
    return baru


def estimasi_naik_pct(stat: dict[str, Any], delta: dict[str, float], s_test: dict, pb: dict[str, Any]) -> float:
    """Estimasi perubahan DPS dalam persen (mis. +4.2 berarti +4.2% DPS)."""
    awal = hitung_komponen(stat, s_test, pb)["skor"]
    if awal <= 0:
        return 0.0
    sesudah = hitung_komponen(terapkan_delta(stat, delta, pb), s_test, pb)["skor"]
    return (sesudah / awal - 1.0) * 100.0


# ------------------------------------------------------------ prioritas stat & bottleneck

def prioritas_stat(stat: dict[str, Any], s_test: dict, job: str = "",
                   sumber_skill: list[dict] | None = None) -> tuple[list[dict], list[str], dict]:
    """Hitung stat mana yang paling besar efek kenaikan DPS-nya + daftar peringatan cap/bottleneck.
    Hasil: (daftar_terurut, peringatan, profil_build)."""
    pb = profil_build(stat, job, sumber_skill)
    magic = pb["magic"]
    ranged = pb["ranged"]
    ras = s_test.get("ras", "Human")
    ukuran = s_test.get("ukuran", "Medium")
    ele_s = s_test.get("elemen", "Neutral")

    # Daftar uji penambahan standar (biaya kira-kira setara)
    uji: list[tuple[str, dict[str, float], str]] = [
        ("Final DMG +5%", {"Final MDMG" if magic else "Final PDMG": 5.0}, "Final DMG +5%"),
        (f"DMG vs {ras} +5%", {f"DMG vs {ras}%": 5.0}, f"vs {ras} +5%"),
        (f"DMG vs {ukuran} +5%", {f"DMG vs {ukuran}%": 5.0}, f"vs {ukuran} +5%"),
        (f"DMG vs {ele_s} +5%", {f"DMG vs {ele_s}%": 5.0}, f"vs {ele_s} +5%"),
        ("Elemental DMG +5%", {"Elemental DMG%": 5.0}, "Elemental DMG +5%"),
        ("M.DMG Bonus +5%" if magic else "P.DMG Bonus +5%",
         {"MDMG Bonus%" if magic else "PDMG Bonus%": 5.0},
         "MDMG% +5%" if magic else "PDMG% +5%"),
        ("M.ATK% +5%" if magic else "ATK% +5%",
         {"M.ATK%" if magic else "ATK%": 5.0},
         "M.ATK% +5%" if magic else "ATK% +5%"),
        ("M.ATK +150" if magic else "ATK +150",
         {"M.ATK" if magic else "ATK": 150.0},
         "M.ATK +150" if magic else "ATK +150"),
        ("Skill DMG +5%", {"Skill DMG%": 5.0}, "Skill DMG% +5%"),
        ("Ignore M.DEF +10%" if magic else "Ignore P.DEF +10%",
         {"Ignore M.DEF%" if magic else "Ignore P.DEF%": 10.0},
         "Ign M.DEF +10%" if magic else "Ign P.DEF +10%"),
    ]
    if not magic:
        uji.append(("CRIT DMG +10%", {"CRIT DMG%": 10.0}, "CRIT DMG +10%"))
        uji.append(("CRIT +10", {"CRIT": 10.0}, "CRIT +10"))
        if ranged:
            uji.append(("Ranged PDMG +5%", {"Ranged PDMG%": 5.0}, "Ranged PDMG +5%"))
        else:
            uji.append(("Melee PDMG +5%", {"Melee PDMG%": 5.0}, "Melee PDMG +5%"))
        if pb["porsi_skill"] < 0.75:
            uji.append(("Normal ATK DMG +5%", {"Normal Attack DMG%": 5.0}, "Normal DMG +5%"))
            if _f(stat.get("Attack Frequency")) > 0:
                uji.append(("Attack Freq +0.5", {"Attack Frequency": 0.5}, "Atk Freq +0.5"))

    hasil = []
    for label, delta, singkat in uji:
        naik = estimasi_naik_pct(stat, delta, s_test, pb)
        if naik > 0.05:
            hasil.append({"label": label, "singkat": singkat, "naik_pct": round(naik, 2), "delta": delta})
    hasil.sort(key=lambda x: -x["naik_pct"])

    # Peringatan cap / stat jenuh
    peringatan = []
    k = hitung_komponen(stat, s_test, pb)
    freq = _f(stat.get("Attack Frequency"))
    if not magic and freq >= 6.8:
        peringatan.append(f"⚠️ Attack Frequency ({freq:g}) sudah mendekati/mentok batas 7,0 — jangan tambah ASPD/AGI lagi.")
    vct = _f(stat.get("Variable Cast Time%"))
    if magic and vct <= -99.0:
        peringatan.append(f"✅ Variable Cast Time ({vct:g}%) sudah mentok -100% — alihkan stat cast time ke M.ATK/MDMG.")
    if k["def_eff"] <= 1.0:
        nama_ign = "Ignore M.DEF" if magic else "Ignore P.DEF"
        peringatan.append(f"ℹ️ {nama_ign} sudah menembus penuh DEF dummy — tambahan Ignore DEF tidak naikkan angka test dummy.")
    if not magic and _f(stat.get("CRIT")) >= 100:
        peringatan.append("ℹ️ CRIT sudah ≥100 — fokus ke CRIT DMG% daripada tambah CRIT lagi.")

    return hasil, peringatan, pb


# ------------------------------------------------------------ parser & simulasi /sim

_ALIAS_STAT = [
    (r"(?:crit\s*dmg|cdmg)", "CRIT DMG%"),
    (r"(?:crit\b|cr\b)", "CRIT"),
    (r"(?:final\s*mdmg)", "Final MDMG"),
    (r"(?:final\s*pdmg)", "Final PDMG"),
    (r"(?:final\s*dmg|final|fdmg)", "Final DMG"),
    (r"(?:ignore\s*m\.?def|ign\s*mdef|mpen)", "Ignore M.DEF%"),
    (r"(?:ignore\s*p\.?def|ign\s*pdef|ignore\s*def|ign\s*def|pen)", "Ignore P.DEF%"),
    (r"(?:ranged\s*pdmg|ranged)", "Ranged PDMG%"),
    (r"(?:melee\s*pdmg|melee)", "Melee PDMG%"),
    (r"(?:mdmg|m\.?dmg)", "MDMG Bonus%"),
    (r"(?:pdmg|p\.?dmg)", "PDMG Bonus%"),
    (r"(?:m\.?atk%|matk%)", "M.ATK%"),
    (r"(?:m\.?atk|matk)", "M.ATK"),
    (r"(?:atk%)", "ATK%"),
    (r"(?:atk)", "ATK"),
    (r"(?:skill\s*dmg|skill)", "Skill DMG%"),
    (r"(?:normal\s*attack|normal\s*dmg|normal|auto)", "Normal Attack DMG%"),
    (r"(?:ele(?:mental)?\s*dmg|ele(?:mental)?)", "Elemental DMG%"),
    (r"(?:vs\s*demi-?human|demi-?human|vs\s*human|human)", "DMG vs Human%"),
    (r"(?:vs\s*medium|medium|med)", "DMG vs Medium%"),
    (r"(?:vs\s*small|small)", "DMG vs Small%"),
    (r"(?:vs\s*large|large)", "DMG vs Large%"),
    (r"(?:vs\s*neutral)", "DMG vs Neutral%"),
    (r"(?:freq|aspd)", "Attack Frequency"),
]


def parse_sim(teks: str) -> dict[str, float]:
    """Parse input seperti '+10% pdmg +20% crit dmg +300 matk -5% atk%' -> {nama_stat: delta}."""
    delta: dict[str, float] = {}
    pola = re.compile(r"([+-]?\d+(?:[.,]\d+)?)\s*(%?)\s*([a-zA-Z.% -]+?)(?=\s*[+-]\d|$)")
    for m in pola.finditer(teks.strip()):
        nilai = float(m.group(1).replace(",", "."))
        ada_persen = bool(m.group(2))
        nama_raw = m.group(3).strip().lower()
        cocok = None
        for rgx, resmi in _ALIAS_STAT:
            if re.search(rgx, nama_raw):
                cocok = resmi
                break
        if not cocok:
            for e in ELEMEN_DAFTAR:
                if e.lower() in nama_raw:
                    cocok = f"DMG vs {e}%" if "vs" in nama_raw else f"{e} DMG%"
                    break
        if not cocok:
            continue
        # Bedakan ATK vs ATK% (dan M.ATK vs M.ATK%) dari tanda %
        if cocok == "ATK" and ada_persen:
            cocok = "ATK%"
        elif cocok == "M.ATK" and ada_persen:
            cocok = "M.ATK%"
        delta[cocok] = delta.get(cocok, 0.0) + nilai
    return delta


def teks_simulasi(pid: str, profil: dict, stat: dict[str, Any], delta: dict[str, float],
                  s_test: dict, sumber_skill: list[dict] | None = None) -> list[str]:
    """Jalankan simulasi What-If dan kembalikan baris HTML untuk Telegram."""
    nama = profil.get("nick") or profil.get("nama") or pid
    job = profil.get("job") or ""
    pb = profil_build(stat, job, sumber_skill)
    naik = estimasi_naik_pct(stat, delta, s_test, pb)

    ok = catatan.baca_ok(pid)
    dps_acuan = ok[-1]["dps"] if ok else 0
    rekor = max((r["dps"] for r in ok), default=0)
    target = profil.get("target") or 0

    tipe = "Magic" if pb["magic"] else ("Fisik Ranged" if pb["ranged"] else "Fisik Melee")
    baris = [f"🧮 <b>Simulasi DPS: {nama}</b>" + (f" ({job})" if job else f" [{tipe}]")]
    ubah_teks = []
    for k, dv in delta.items():
        persen = "%" if k.endswith("%") or k in ("Final DMG", "Final PDMG", "Final MDMG") else ""
        lama = _f(stat.get(k))
        ubah_teks.append(f"• {k}: {lama:g}{persen} → <b>{lama + dv:g}{persen}</b> ({dv:+g}{persen})")
    baris += ubah_teks

    tanda = "📈" if naik >= 0 else "📉"
    baris.append(f"\n{tanda} Estimasi perubahan DPS: <b>{naik:+.2f}%</b>")
    if dps_acuan:
        baru_akhir = round(dps_acuan * (1 + naik / 100.0))
        baris.append(f"• Dari DPS terakhir ({umum.fmt(dps_acuan)}) → ±<b>{umum.fmt(baru_akhir)}</b>")
    if rekor and rekor != dps_acuan:
        baru_rekor = round(rekor * (1 + naik / 100.0))
        baris.append(f"• Dari rekor ({umum.fmt(rekor)}) → ±<b>{umum.fmt(baru_rekor)}</b>")
    if target and (dps_acuan or rekor):
        patokan = max(dps_acuan, rekor)
        proyeksi = round(patokan * (1 + naik / 100.0))
        if proyeksi >= target:
            baris.append(f"🎯 Proyeksi <b>TEMBUS</b> target {umum.fmt(target)}!")
        else:
            kurang = target - proyeksi
            baris.append(f"🎯 Masih kurang ±{umum.fmt(kurang)} (+{(target / proyeksi - 1) * 100:.1f}%) ke target {umum.fmt(target)}.")
    baris.append("ℹ️ <i>Perkiraan model multi-bucket RTNW (belum termasuk perubahan rotasi/proc buff).</i>")
    return baris


# ------------------------------------------------------------ kalibrasi dari data nyata

def kalibrasi(pid: str, s_test: dict, job: str = "") -> dict[str, Any] | None:
    """Bandingkan prediksi model vs hasil test nyata di data/<pid>/test_stat.jsonl."""
    f = catatan.folder_profil(pid) / "test_stat.jsonl"
    if not f.exists():
        return None
    entri = []
    for b in f.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(b)
            if d.get("dps") and d.get("stat"):
                entri.append(d)
        except ValueError:
            continue
    if len(entri) < 2:
        return None

    galat = []
    for a, b in zip(entri, entri[1:]):
        if a["stat"] == b["stat"] or not a["dps"]:
            continue
        pb = profil_build(a["stat"], job)
        s_a = hitung_komponen(a["stat"], s_test, pb)["skor"]
        s_b = hitung_komponen(b["stat"], s_test, pb)["skor"]
        if s_a <= 0:
            continue
        pred = (s_b / s_a - 1.0) * 100.0
        nyata = (b["dps"] / a["dps"] - 1.0) * 100.0
        if abs(nyata) >= 3.0:
            galat.append(abs(pred - nyata))
    if not galat:
        return None
    return {"jumlah_pasang": len(galat), "rata_galat_pct": round(sum(galat) / len(galat), 2)}
