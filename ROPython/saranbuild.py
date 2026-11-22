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


def saran(pid: str, profil: dict, sasaran_test: dict) -> list[str]:
    import bacabuild
    import rumus
    import sasaran
    import statistik
    nama = profil.get("nick") or profil.get("nama") or pid
    job = profil.get("job") or ""
    baris = [f"🧭 <b>Saran build: {nama}</b>" + (f" ({job})" if job else "")]
    baris += _ringkas_dps(pid, profil.get("target"))

    # Data panel Statistics terakhir (damage per skill), jika ada
    stat_log = statistik.baca_log(pid)
    sumber_skill = stat_log[-1].get("sumber") if stat_log else None
    if sumber_skill:
        top = sumber_skill[:3]
        baris += ["", "⚡ Damage utama (Statistics): " + ", ".join(f"{r['nama']} {r['persen']:g}%" for r in top)]

    # Stat vs sasaran + simulasi prioritas stat (rumus.py)
    log = bacabuild.baca_log(pid)
    is_magic = False
    if log:
        st = {}
        for _, s in log:
            st.update(s)
        an = sasaran.analisis(st, sasaran_test)
        if an:
            baris += ["", f"📊 Stat (terakhir dibaca {log[-1][0]:%d/%m %H:%M}):"] + an
        prio, warn, pb = rumus.prioritas_stat(st, sasaran_test, job, sumber_skill)
        is_magic = pb["magic"]
        if prio:
            tipe = "Magic" if pb["magic"] else ("Fisik Ranged" if pb["ranged"] else "Fisik Melee")
            baris += ["", f"🧮 Prioritas naik stat ({tipe}, simulasi DPS):"]
            for i, p in enumerate(prio[:4], 1):
                baris.append(f"{i}. {p['label']} → est. <b>+{p['naik_pct']:.2f}% DPS</b>")
            baris += warn[:2]
            baris.append("   Ketik <code>/sim +10% pdmg</code> (atau stat lain) untuk hitung proyeksi DPS.")
    else:
        baris += ["", "📊 Stat belum tersimpan → buka Character Info > Detailed Stats sekali."]

    # Enchant
    items, sumber = build_karakter(pid)
    if items:
        e = saran_enchant(items)
        baris += ["", f"💎 Enchant (dari {sumber}):"] + (e or ["Semua set DPS sudah optimal untuk data yang terlihat."])
        if is_magic:
            baris.append("ℹ️ Karakter Magic: pastikan pilih gem/set M.ATK & MDMG (data set Magic terisi otomatis saat halaman Enchant dibuka).")
    else:
        baris += ["", "💎 Enchant belum terlihat → buka halaman Enchant (pilih Weapon/Acc/Head/Back)."]
    return baris
