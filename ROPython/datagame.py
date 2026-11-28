"""Database equip / kartu / skill Ragnarok: The New World (server SEA).

Sumber: https://roworlddb.com/sea/  (database buatan komunitas, BUKAN resmi Gravity).
Datanya file JSON yang juga dipakai situs itu sendiri. Disimpan di folder database/.

- Tidak menyentuh game sama sekali (hanya mengunduh dari internet).
- `perbarui()` hanya mengunduh ulang kalau situsnya sudah update (versi berubah).

Jalankan langsung untuk memperbarui:  python datagame.py   (atau 8_perbarui_database.bat)
Paksa unduh ulang:                     python datagame.py --paksa
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import umum

SITUS = "https://roworlddb.com"
BAHASA = "en-US"  # sama dengan bahasa di game, supaya nama item cocok dengan yang terbaca di layar
FOLDER_DB = umum.FOLDER / "database"
FILE_VERSI = FOLDER_DB / "versi.json"
HEADER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ROPython-database/1.0"}

FILE_DATA = {
    "equipment.json": f"/sea/equipment/data/equipment_{BAHASA}.json",
    "kartu.json": f"/sea/card-simulator/data/handbook_cards_{BAHASA}.json",
    "skill_index.json": f"/sea/skill-simulator/data/skills_index_{BAHASA}.json",
}
_kunci = threading.Lock()


class DatabaseError(Exception):
    pass


# ------------------------------------------------------------ unduh / perbarui

def _get(sesi, path: str, versi: str = "", json_: bool = True):
    url = SITUS + path + (f"?v={versi}" if versi else "")
    for coba in range(3):
        try:
            r = sesi.get(url, headers=HEADER, timeout=60)
            r.raise_for_status()
            return r.json() if json_ else r.text
        except Exception as e:  # noqa: BLE001
            if coba == 2:
                raise DatabaseError(f"Gagal mengunduh {path}: {e}") from None
            time.sleep(2 * (coba + 1))


def versi_situs(sesi=None) -> str:
    import requests
    sesi = sesi or requests.Session()
    html = _get(sesi, "/sea/equipment/", json_=False)
    m = re.search(r"\?v=(\d{8}-\d{6})", html)
    if not m:
        raise DatabaseError("Versi data di situs tidak ditemukan (tampilan situs mungkin berubah).")
    return m.group(1)


def info_lokal() -> dict:
    try:
        return umum.json_loads(FILE_VERSI.read_bytes())
    except Exception:
        return {}


def perbarui(paksa: bool = False, log=print) -> tuple[bool, str]:
    """Unduh database kalau situsnya sudah update. Hasil: (ada perubahan?, pesan)."""
    import requests
    with _kunci:
        sesi = requests.Session()
        versi = versi_situs(sesi)
        lama = info_lokal()
        if not paksa and lama.get("versi") == versi and all((FOLDER_DB / f).exists() for f in FILE_DATA):
            lama["dicek"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            FILE_VERSI.write_text(json.dumps(lama, indent=2, ensure_ascii=False), encoding="utf-8")
            return False, f"Database sudah terbaru (versi {versi})."

        log(f"Mengunduh database versi {versi} dari {SITUS} ...")
        baru = FOLDER_DB.with_name("database_unduh")
        shutil.rmtree(baru, ignore_errors=True)
        (baru / "skill").mkdir(parents=True)
        data = {}
        for nama, path in FILE_DATA.items():
            data[nama] = _get(sesi, path, versi)
            (baru / nama).write_text(json.dumps(data[nama], ensure_ascii=False), encoding="utf-8")
            log(f"  {nama} OK")
        jobs = [j for j in data["skill_index.json"]["jobs"].values() if j.get("has_skills")]
        for j in jobs:
            isi = _get(sesi, f"/sea/skill-simulator/data/jobs_{BAHASA}/{j['job_id']}.json", versi)
            (baru / "skill" / f"{j['job_id']}.json").write_text(json.dumps(isi, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.2)  # sopan ke server situs
        log(f"  skill {len(jobs)} job OK")
        _unduh_gem(sesi, versi, baru)
        log("  gem OK")

        info = {"versi": versi, "sumber": SITUS + "/sea/", "bahasa": BAHASA,
                "diunduh": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "dicek": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "jumlah": {"equipment": len(data["equipment.json"]["items"]),
                           "kartu": len(data["kartu.json"]["cards"]), "job": len(jobs)}}
        (baru / "versi.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
        # Ganti folder lama sekaligus, supaya tidak pernah setengah-lama setengah-baru.
        cadangan = FOLDER_DB.with_name("database_lama")
        shutil.rmtree(cadangan, ignore_errors=True)
        if FOLDER_DB.exists():
            os.replace(FOLDER_DB, cadangan)
        os.replace(baru, FOLDER_DB)
        shutil.rmtree(cadangan, ignore_errors=True)
        _cache.clear()
        j = info["jumlah"]
        return True, (f"Database diperbarui ke versi {versi}: {j['equipment']} equipment, "
                      f"{j['kartu']} kartu, skill {j['job']} job.")


FOLDER_IKON = umum.FOLDER / "database_ikon"  # terpisah, supaya tidak ikut terhapus saat database diganti


def ikon_dibutuhkan() -> dict[str, str]:
    """{nama ikon: 'equip'/'kartu'} untuk semua equip (bukan shadow) dan kartu."""
    hasil = {i["icon"]: "equip" for i in _muat("equipment.json")["items"] if not i.get("isShadow") and i.get("icon")}
    hasil.update({c["item_icon"]: "kartu" for c in _muat("kartu.json")["cards"] if c.get("item_icon")})
    try:
        hasil.update({g["icon"].split("/")[-1]: "gem" for g in _muat("gem.json") if g.get("icon")})
    except Exception:
        pass
    return hasil


def unduh_ikon(log=print) -> int:
    """Unduh gambar ikon equip & kartu yang belum ada (untuk mengenali ikon di layar game).
    Hasil: jumlah ikon yang baru diunduh."""
    import requests
    sesi = requests.Session()
    FOLDER_IKON.mkdir(parents=True, exist_ok=True)
    versi = info_lokal().get("versi", "")
    peta = _get(sesi, "/sea/skill-simulator/data/icon_paths.json", versi)
    perlu = [n for n in ikon_dibutuhkan() if not (FOLDER_IKON / f"{n}.webp").exists()]
    if perlu:
        log(f"Mengunduh {len(perlu)} ikon ...")
    baru = 0
    for n in perlu:
        path = peta.get(n) or peta.get(n.lower())
        url = SITUS + ("/media/images/" + str(path).replace("\\", "/") if path else f"/media/images/item/{n}.png")
        url = re.sub(r"\.png$", ".webp", url, flags=re.I)
        try:
            r = sesi.get(url, headers=HEADER, timeout=30)
            if r.status_code == 200 and r.content:
                (FOLDER_IKON / f"{n}.webp").write_bytes(r.content)
                baru += 1
        except Exception as e:  # noqa: BLE001
            log(f"  ikon {n} gagal: {e}")
        time.sleep(0.05)  # sopan ke server situs
    return baru


def _unduh_gem(sesi, versi: str, folder: Path) -> None:
    """Daftar gem enchant (item tipe 41) dari daftar item situs -> folder/gem.json."""
    items = _get(sesi, f"/sea/items/data/items_{BAHASA}.json", versi)["items"]
    gem = [{"id": i["i"], "name": i["n"], "quality": i["q"], "level": i.get("lv"), "icon": i.get("ic")}
           for i in items if i.get("t") == 41]
    (folder / "gem.json").write_text(json.dumps(gem, ensure_ascii=False), encoding="utf-8")


FILE_ENCHANT = umum.FOLDER / "database_lokal" / "enchant.json"


def enchant_lokal(gabung: bool = True) -> dict:
    """Database enchant yang dipelajari dari layar game (set, gem per level). Boleh diedit manual.
    gabung=True: ikut sertakan hasil belajar otomatis bot (database_lokal/enchant_belajar.json)."""
    try:
        db = umum.json_loads(FILE_ENCHANT.read_bytes())
    except Exception:
        db = {"gem": {}, "set": {}}
    if not gabung:
        return db
    try:
        import belajar
        b = belajar.ringkas()
    except Exception:
        return db
    for nama, lv in b.get("set", {}).items():
        s = db.setdefault("set", {}).setdefault(nama, {"gem": [], "fokus": None})
        s.setdefault("level", {})
        for k, efek in lv.items():
            s["level"].setdefault(k, efek)  # data yang dicek manual tetap diutamakan
        s["dipelajari"] = True
    for nama, info in b.get("gem", {}).items():
        db.setdefault("gem", {}).setdefault(nama, {})["dipelajari"] = info
    return db


def perlu_cek(jam: float = 24) -> bool:
    """True kalau terakhir dicek lebih dari `jam` jam lalu (atau belum pernah)."""
    try:
        dicek = datetime.strptime(info_lokal()["dicek"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return True
    return (datetime.now() - dicek).total_seconds() >= jam * 3600


# ------------------------------------------------------------ baca

_cache: dict = {}


def _muat(nama: str):
    if nama not in _cache:
        f = FOLDER_DB / nama
        if nama == "gem.json" and not f.exists() and FOLDER_DB.exists():
            import requests  # database lama (sebelum ada gem): ambil daftar gem saja
            _unduh_gem(requests.Session(), info_lokal().get("versi", ""), FOLDER_DB)
        if not f.exists():
            raise DatabaseError("Database belum diunduh. Jalankan 8_perbarui_database.bat")
        _cache[nama] = umum.json_loads(f.read_bytes())
    return _cache[nama]


def _skill_semua() -> list[dict]:
    """Semua skill dari semua job: [{job_id, job, id, nama, data}]."""
    if "_skill" not in _cache:
        hasil = []
        for f in sorted((FOLDER_DB / "skill").glob("*.json")):
            j = umum.json_loads(f.read_bytes())
            for kel in ("skills", "unique_skills"):
                isi = j.get(kel) or {}
                for sid, s in (isi.items() if isinstance(isi, dict) else enumerate(isi)):
                    if isinstance(s, dict) and s.get("name"):
                        hasil.append({"job_id": j["job_id"], "job": j["job_name"], "id": sid,
                                      "nama": s["name"], "data": s})
        _cache["_skill"] = hasil
    return _cache["_skill"]


def bersihkan(teks) -> str:
    """Buang tag warna <color=...> dari teks game."""
    return re.sub(r"</?color[^>]*>", "", str(teks or "")).strip()


def _angka(x: float) -> str:
    if abs(x % 1) < 1e-4:
        return str(int(x))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def format_stat(attr_id, nilai) -> str:
    """Angka mentah stat -> teks seperti di game (sama dengan cara roworlddb menampilkannya)."""
    a = _muat("equipment.json")["attributes"].get(str(attr_id)) or {"name": f"Stat {attr_id}"}
    n = float(nilai)
    tampil, desimal = int(a.get("percentage_show") or 0), int(a.get("reserve_number") or 0)

    def persen(kali: float) -> str:
        from decimal import ROUND_HALF_UP, Decimal
        x = n * kali
        if desimal == 0 or n // 1 == 0:
            return f"{_angka(float(int(x)))}%"
        if not float(x).is_integer():  # sama dengan toFixed(1) di JavaScript
            x = float(Decimal(x).quantize(Decimal("0.1"), ROUND_HALF_UP))
        return f"{_angka(x)}%"

    if tampil == 0:
        teks = _angka(n)
    elif tampil == 1:
        teks = persen(0.01)
    elif tampil == 3:
        teks = persen(0.25)
    elif tampil == 4:
        teks = _angka(float(int(abs(n) * 0.1)) * (-1 if n < 0 else 1))
    elif tampil == 5:
        teks = _angka((n * 0.01 // 1) / 100)
    else:
        teks = _angka(float(int(abs(n) * 0.01)) * (-1 if n < 0 else 1))
    tanda = "" if teks.startswith("-") else "+"
    return f"{a['name']} {tanda}{teks}"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _mirip(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def skor_nama(q: str, nama: str) -> float:
    """Seberapa cocok ketikan `q` dengan `nama` (0..1). Longgar: salah ketik, kata terbalik,
    singkatan awal kata ('dom gem'), tanpa spasi ('swiftattack'), angka romawi ('3' = 'III')."""
    n = _norm(nama)
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    rapat_q, rapat_n = q.replace(" ", ""), n.replace(" ", "")
    if q in n or rapat_q in rapat_n:
        return 0.9 + 0.09 * len(rapat_q) / max(len(rapat_n), 1)
    kata_n = n.split()
    nilai = []
    for w in q.split():
        terbaik = 0.0
        for x in kata_n:
            if x.startswith(w) and len(w) >= 2:
                s = 0.93
            else:
                s = _mirip(w, x)
            terbaik = max(terbaik, s)
        nilai.append(terbaik)
    per_kata = sum(nilai) / len(nilai)
    # semua kata nama ikut diketik? (supaya 'acid' tidak sama kuat dengan 'acid terror')
    cakup = min(1.0, len(q.split()) / max(len(kata_n), 1))
    return max(per_kata * (0.82 + 0.1 * cakup), _mirip(rapat_q, rapat_n) * 0.9, _mirip(q, n) * 0.88)


_ROMAWI = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v"}


def _ketikan(teks: str) -> str:
    """Rapikan ketikan: 'swift atk 2' -> 'swift atk ii', 'lv' dibuang."""
    kata = [_ROMAWI.get(w, w) for w in _norm(teks).split() if w not in ("lv", "level")]
    return " ".join(kata)


def cari(teks: str, jenis: str | None = None, batas: int = 5) -> list[dict]:
    """Cari equip / kartu / skill / gem / set enchant / rune / pet / apocalypse / affix berdasarkan nama.
    Tahan salah ketik. Hasil urut paling cocok: [{jenis, id, nama, skor, data, (job)}]."""
    q = _ketikan(teks)
    if not q:
        return []
    calon: list[dict] = []
    if jenis in (None, "equip"):
        calon += [{"jenis": "equip", "id": i["id"], "nama": i["name"], "data": i}
                  for i in _muat("equipment.json")["items"]]
    if jenis in (None, "kartu"):
        calon += [{"jenis": "kartu", "id": c["id"], "nama": c["name"], "data": c}
                  for c in _muat("kartu.json")["cards"]]
    if jenis in (None, "skill"):
        calon += [dict(s, jenis="skill") for s in _skill_semua()]
    if jenis in (None, "gem"):
        try:
            calon += [{"jenis": "gem", "id": g["id"], "nama": g["name"], "data": g} for g in _muat("gem.json")]
        except Exception:
            pass  # daftar gem belum ada (internet mati saat pertama kali) -> lewati
    if jenis in (None, "enchant"):
        calon += [{"jenis": "enchant", "id": n, "nama": n, "data": d} for n, d in enchant_lokal().get("set", {}).items()]
    hasil = []
    for c in calon:
        skor = skor_nama(q, c["nama"])
        if skor >= 0.55:
            hasil.append(dict(c, skor=round(skor, 3)))
    if jenis in (None, "rune", "pet", "apocalypse", "apoc", "affix", "stunt"):
        try:
            import datartnw
            for h in datartnw.cari_tambahan(q, jenis or ""):
                if h["skor"] >= 0.55:
                    hasil.append(dict(h, id=h["nama"], skor=round(h["skor"], 3)))
        except Exception:
            pass
    hasil.sort(key=lambda h: (-h["skor"], len(h["nama"])))
    # Skill yang sama di beberapa job: tampilkan sekali saja.
    unik, lihat = [], set()
    for h in hasil:
        kunci = (h["jenis"], _norm(h["nama"]), h["data"].get("stats") and str(h["data"]["stats"]) if isinstance(h["data"], dict) else None)
        if kunci in lihat:
            continue
        lihat.add(kunci)
        unik.append(h)
    return unik[:batas]


KUALITAS = {1: "Biasa", 2: "Hijau", 3: "Biru", 4: "Ungu", 5: "Emas", 6: "Merah"}  # warna seperti di roworlddb


def kualitas(item: dict) -> str:
    return KUALITAS.get(item.get("quality"), "")


def nama_job(job_id) -> str:
    j = _muat("equipment.json")["jobs"].get(str(job_id))
    return j["name"] if j else str(job_id)


def teks_equip(i: dict) -> list[str]:
    eq = _muat("equipment.json")
    slot = (eq["itemTypes"].get(str(i.get("itemType"))) or {}).get("name") \
        or (eq["assemblyTypes"].get(str(i.get("assemblyType"))) or {}).get("name") or ""
    ket = ", ".join(x for x in (kualitas(i), f"Lv.{i['openLevel']}" if i.get("openLevel") else "") if x)
    baris = [f"{i['name']}" + (f" - {slot}" if slot else "") + (f" ({ket})" if ket else "")]
    if i.get("jobLimits"):
        baris.append("Job: " + ", ".join(nama_job(j) for j in i["jobLimits"]))
    baris += [format_stat(a, v) for a, v in i.get("stats") or []]
    for kel, kolom in (("conditions", "text"), ("buffs", "desc"), ("stunts", "desc")):
        for x in i.get(kel) or []:
            d = eq[kel].get(str(x)) or {}
            t = bersihkan(d.get(kolom))
            if t:
                baris.append(("• " + d["name"] + ": " if d.get("name") and kel != "conditions" else "• ") + t)
    for x in i.get("specialEffects") or []:
        t = bersihkan(eq["specialEffects"].get(str(x)))
        if t:
            baris.append("• " + t)
    if i.get("fixedAffixes"):
        for a in i["fixedAffixes"]:
            for at in (eq["affixes"].get(str(a)) or {}).get("attrs") or []:
                baris.append(f"Affix: {format_stat(at['attrId'], at['min'])} ~ {format_stat(at['attrId'], at['max']).split()[-1]}")
    if i.get("randomAffixRange"):
        lo, hi = i["randomAffixRange"]
        baris.append(f"Affix acak: {lo}" + (f"-{hi}" if hi != lo else ""))
    suits = {s["id"]: s for s in eq["suits"]} if isinstance(eq["suits"], list) else {}
    for s in i.get("suits") or []:
        if s in suits:
            baris.append(f"Set: {suits[s]['name']}")
    try:
        import datartnw
        r1 = datartnw.teks_refine(i.get("id"), 1)
        if r1:
            r10 = datartnw.teks_refine(i.get("id"), 10)
            baris.append(f"Refine +1: {', '.join(r1)} (+10: {', '.join(r10)})")
    except Exception:
        pass
    return baris


def teks_kartu(c: dict) -> list[str]:
    return [f"{c['name']} - slot {c.get('card_type_name') or '?'}"] + [bersihkan(x) for x in c.get("effect_lines") or []]


def teks_skill(s: dict) -> list[str]:
    d = s["data"]
    lv = d.get("levels") or {}
    baris = [f"{d['name']} ({s['job']}) - maks Lv.{d.get('max_level') or d.get('natural_max_level') or '?'}"]
    if lv:
        kunci = sorted(lv, key=lambda k: int(k))
        awal, akhir = lv[kunci[0]], lv[kunci[-1]]
        if awal.get("pve_percent") is not None:
            baris.append(f"Damage PvE: Lv.{kunci[0]} {_angka(awal['pve_percent'])}% → Lv.{kunci[-1]} "
                         f"{_angka(akhir['pve_percent'])}%")
        if akhir.get("cooldown") is not None:
            baris.append(f"Cooldown {_angka(akhir['cooldown'] / 1000)} dtk, SP {akhir.get('mana_cost', '?')}")
        baris.append(bersihkan(akhir.get("des") or d.get("skilldes")))
    else:
        baris.append(bersihkan(d.get("skilldes") or d.get("des")))
    return baris


def _angka_gem(info: dict, lv: int) -> str:
    v = info["per_level"] * lv
    return f"{info['stat']} +{_angka(v)}{'%' if info.get('persen') else ''}"


def teks_gem(g: dict) -> list[str]:
    db = enchant_lokal()
    info = db.get("gem", {}).get(g["name"])
    id_ = int(g.get("id") or 0)
    jenis = "Shadow Gear" if "Shadow Gear" in g["name"] else ("premium" if g.get("quality", 0) >= 5 else "biasa")
    baris = [f"{g['name']} - gem enchant {jenis} ({KUALITAS.get(g.get('quality'), '?')})"]
    urut = db.get("urutan_dialog_premium", [])
    if g["name"] in urut:
        baris.append(f"Urutan di dialog Replace Enchant Stone: ke-{urut.index(g['name']) + 1} dari {len(urut)}")
    belajar = (info or {}).get("dipelajari") or {}
    if info and info.get("stat"):
        baris.append(f"Per level (dari layar game): {_angka_gem(info, 1)}  (Lv.5 = {_angka_gem(info, 5)})")
        if info.get("slot"):
            baris.append("Bisa dipasang di: " + ", ".join(info["slot"])
                         + " (menurut detail gem; slot Combat seperti Headwear/Facewear/Mouthwear/Backwear juga terlihat bisa)")
    if belajar:
        baris.append("🧠 Dibaca otomatis dari layar game:")
        if belajar.get("deskripsi"):
            baris.append(f"   \"{belajar['deskripsi']}\"")
        if belajar.get("slot") and not (info or {}).get("slot"):
            baris.append("   Slot: " + ", ".join(belajar["slot"]))
        if belajar.get("stat"):
            baris.append("   Gem Stats terakhir terlihat: " + ", ".join(belajar["stat"]))
    if not (info and info.get("stat")) and not belajar:
        baris.append("Angka stat per level belum tercatat (tekan lama ikonnya di game untuk melihat detailnya).")
        kisar = db.get("kisaran_umum_belum_dicek", {}).get("gem_premium" if jenis == "premium" else "gem_biasa")
        if kisar and jenis != "Shadow Gear":
            baris.append(f"Kisaran umum gem {jenis} (panduan komunitas, belum dicek): {kisar}")
    if id_:
        baris.append(f"ID item: {id_}")
    dipakai = [n for n, s in db.get("set", {}).items() if g["name"] in s.get("gem", [])]
    if dipakai:
        baris.append("Dipakai di set: " + ", ".join(dipakai))
    return baris


def teks_enchant(nama: str, s: dict) -> list[str]:
    db = enchant_lokal()
    fokus = {"DPS": " ⚔️ menambah damage", "bertahan": " 🛡 bertahan (HP/DEF), tidak menambah DPS"}.get(s.get("fokus"), "")
    baris = [f"{nama} - set enchant" + (f" [{s['label_game']}]" if s.get("label_game") else "")]
    baris.append("Gem: " + " + ".join(s.get("gem", [])))
    slot = s.get("slot") or s.get("terlihat_di")
    if slot:
        baris.append("Slot: " + ", ".join(slot) + fokus)
    if s.get("per_level"):
        baris.append(f"Per level set: {s['per_level']}")
    for lv, efek in sorted(s.get("level", {}).items(), key=lambda kv: int(kv[0])):
        stone = [_angka_gem(db["gem"][g], int(lv)) for g in s.get("gem", []) if db.get("gem", {}).get(g, {}).get("stat")]
        baris.append(f"Lv.{lv}: set {efek}" + (f" (+ kalau semua gem Lv.{lv}: {', '.join(stone)})" if stone else ""))
    if not s.get("level"):
        baris.append("Efek per level belum tercatat. Buka halaman Enchant di game (equipment yang set-nya aktif), "
                     "bot akan membacanya otomatis.")
    elif s.get("dipelajari"):
        baris.append("🧠 Sebagian efek dibaca otomatis dari layar game.")
    if s.get("catatan"):
        baris.append(s["catatan"])
    baris.append("ℹ️ Level set = level gem terendah di set itu.")
    return baris


def gambar_ikon(h: dict) -> bytes | None:
    """Gambar ikon (PNG, latar terang) untuk hasil pencarian equip / kartu / gem. None kalau tidak ada."""
    import io
    from PIL import Image
    d = h["data"]
    nama = {"equip": d.get("icon"), "kartu": d.get("item_icon"),
            "gem": (d.get("icon") or "").split("/")[-1]}.get(h["jenis"])
    f = FOLDER_IKON / f"{nama}.webp" if nama else None
    if not f or not f.exists():
        return None
    ikon = Image.open(f).convert("RGBA").resize((256, 256), Image.LANCZOS)
    latar = Image.new("RGBA", ikon.size, (245, 238, 225, 255))
    latar.alpha_composite(ikon)
    buf = io.BytesIO()
    latar.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def teks_hasil(h: dict) -> list[str]:
    if h["jenis"] == "gem":
        return teks_gem(h["data"])
    if h["jenis"] == "enchant":
        return teks_enchant(h["nama"], h["data"])
    if h["jenis"] in ("rune", "pet", "apocalypse", "affix"):
        import datartnw
        return datartnw.teks_tambahan(h)
    return {"equip": teks_equip, "kartu": teks_kartu}.get(h["jenis"], lambda _: teks_skill(h))(h["data"])


def main() -> int:
    umum.siapkan_konsol()
    try:
        _, pesan = perbarui(paksa="--paksa" in sys.argv)
        print(pesan)
        print(f"Ikon baru diunduh: {unduh_ikon()}")
    except DatabaseError as e:
        print("GAGAL:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
