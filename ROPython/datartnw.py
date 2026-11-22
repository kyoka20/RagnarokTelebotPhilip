"""Data tambahan untuk MERAMU build, dari rtnw.online (ekspor data client SEA, komunitas, BUKAN resmi).

Hanya yang menambah stat/damage dan belum ada di database roworlddb:
  • refine.json     stat tambahan per +1 refine tiap equipment (roworlddb tidak punya)
  • rune.json       efek rune per level + resonansi elemen
  • pet.json        stat pet per tingkat bond
  • apocalypse.json trait Apocalypse (stat, slot, job)
  • stunt.json      affix / special skill equipment (StuntAttributeLibrary)
Data monster ada di monster.py. Semua di database_tetap/ (tidak ikut diganti saat database roworlddb
diperbarui; boleh dikirim lewat /update). Perbarui: `python datartnw.py` (butuh internet).
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime

import umum

SITUS = "https://rtnw.online/sea"
BAHASA = "en-US"
FOLDER = umum.FOLDER / "database_tetap"
HEADER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ROPython-database/1.0"}
PATH = {
    "equipment_index": f"/equipment/data/equipment_index_{BAHASA}.json",
    "equipment_chunk": f"/equipment/data/optimized/{BAHASA}/{{}}",
    "rune": f"/skill-simulator/data/engine_runes_{BAHASA}.json",
    "pet": f"/pet/data/pet_library_{BAHASA}.json",
    "apocalypse": f"/apocalypse-simulator/data/apocalypse_planner_{BAHASA}.json",
    "stunt_manifest": f"/affix-simulator/data/stunt_shard_manifest_{BAHASA}.json",
    "stunt_shard": f"/affix-simulator/data/optimized/{BAHASA}/{{}}",
}
_cache: dict = {}

_WARNA_STUNT = {2: "Hijau", 3: "Biru", 4: "Ungu", 5: "Emas", 6: "Merah"}


def _bersih(teks: str | None) -> str:
    return re.sub(r"</?color[^>]*>", "", str(teks or "")).strip()


# ------------------------------------------------------------ susun file ringkas

def _refine(index: dict, ambil_chunk) -> dict:
    out = {}
    for c in sorted({i["_detailChunk"] for i in index["items"]}):
        for it in ambil_chunk(c)["items"]:
            if it.get("refinePerLevel"):
                out[str(it["id"])] = {"nama": it["name"], "per_level": it["refinePerLevel"]}
    return out


def _rune(d: dict) -> dict:
    efek = {g["name"]: {"elemen": d["elements"].get(str(g.get("elementId")), {}).get("name"),
                        "level": {lv: x["desc"] for lv, x in g["levels"].items()}}
            for g in d["effectGroups"].values()}
    resonansi = {e["name"]: e.get("resonance") for e in d["elements"].values()}
    return {"efek": efek, "resonansi": resonansi}


def _pet(d: dict) -> list:
    return [{"nama": p["name"], "kualitas": (p.get("quality") or {}).get("name"),
             "level": [{"lv": l["level"], "judul": l.get("title"), "efek": (l.get("skill") or {}).get("description")}
                       for l in p.get("levels") or []]} for p in d["pets"]]


def _apocalypse(d: dict) -> list:
    return [{"kualitas": e.get("quality"), "kunci": (e.get("keyword") or {}).get("name"), "judul": e.get("title"),
             "efek": e.get("detail_text"), "slot": e.get("part_keys"), "job": e.get("job_labels")}
            for e in d["entries"]]


def _stunt(manifest: dict, ambil_shard) -> list[dict]:
    """Kumpulkan semua affix / special skill equipment dari shard manifest -> list ringkas per nama."""
    kelompok: dict[str, dict] = {}
    shards = sorted(set((manifest.get("packageToShard") or {}).values()))
    for sh in shards:
        d = ambil_shard(sh)
        for pkg in (d.get("packages") or {}).values():
            for ent in pkg.get("entries") or []:
                s = ent.get("stunt") or {}
                nama = (s.get("name") or "").strip()
                if not nama:
                    continue
                warna = _WARNA_STUNT.get(int(s.get("color") or 0), str(s.get("color") or "?"))
                lv = str(s.get("level") or 1)
                desc = _bersih(s.get("desc"))
                k = f"{nama}|{warna}"
                item = kelompok.setdefault(k, {"nama": nama, "warna": warna, "level": {}, "job_count": len(s.get("job_ids") or [])})
                item["level"][lv] = desc
    return sorted(kelompok.values(), key=lambda x: (x["nama"], x["warna"]))


def _simpan_file(nama: str, data) -> None:
    FOLDER.mkdir(exist_ok=True)
    waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (FOLDER / nama).write_text(json.dumps({"sumber": SITUS, "diunduh": waktu, "data": data},
                                          ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def susun(ambil) -> dict[str, int]:
    """ambil(kunci, arg=None) -> json mentah. Tulis semua file ringkas. Hasil: jumlah isi per file."""
    FOLDER.mkdir(exist_ok=True)
    isi = {
        "refine.json": _refine(ambil("equipment_index"), lambda c: ambil("equipment_chunk", c)),
        "rune.json": _rune(ambil("rune")),
        "pet.json": _pet(ambil("pet")),
        "apocalypse.json": _apocalypse(ambil("apocalypse")),
        "stunt.json": _stunt(ambil("stunt_manifest"), lambda s: ambil("stunt_shard", s)),
    }
    for nama, data in isi.items():
        _simpan_file(nama, data)
    _cache.clear()
    return {n: len(d["efek"]) if n == "rune.json" else len(d) for n, d in isi.items()}


def _buat_pengambil():
    """Pengambil JSON dengan requests, otomatis fallback ke curl.exe jika SSL bermasalah."""
    try:
        import requests
        sesi = requests.Session()
    except Exception:
        sesi = None

    def ambil(kunci, arg=None):
        url = SITUS + PATH[kunci].format(arg)
        if sesi is not None:
            try:
                r = sesi.get(url, headers=HEADER, timeout=60)
                r.raise_for_status()
                time.sleep(0.15)
                return r.json()
            except Exception:
                pass
        out = subprocess.check_output(["curl.exe", "-s", "-A", HEADER["User-Agent"], url], timeout=60)
        time.sleep(0.15)
        return json.loads(out.decode("utf-8"))
    return ambil


def perbarui(log=print) -> dict[str, int]:
    jumlah = susun(_buat_pengambil())
    log(f"Data rtnw tersimpan di {FOLDER}: {jumlah}")
    return jumlah


def perbarui_stunt(log=print) -> int:
    """Unduh hanya stunt.json (affix / special skill equipment)."""
    ambil = _buat_pengambil()
    data = _stunt(ambil("stunt_manifest"), lambda s: ambil("stunt_shard", s))
    _simpan_file("stunt.json", data)
    _cache.pop("stunt.json", None)
    log(f"stunt.json tersimpan di {FOLDER}: {len(data)} affix")
    return len(data)


# ------------------------------------------------------------ baca

def muat(nama: str):
    if nama not in _cache:
        try:
            _cache[nama] = json.loads((FOLDER / nama).read_text(encoding="utf-8"))["data"]
        except (OSError, ValueError, KeyError):
            _cache[nama] = {} if nama in ("refine.json", "rune.json") else []
    return _cache[nama]


def refine_per_level(item_id) -> list[tuple[int, float]]:
    """[(attr_id, nilai per +1 refine), ...] untuk equipment ini (kosong kalau tidak ada data)."""
    d = muat("refine.json").get(str(item_id))
    return [tuple(x) for x in d["per_level"]] if d else []


def teks_refine(item_id, refine: int) -> list[str]:
    """Stat tambahan dari refine +N, teks seperti di game, mis. ['ATK +30', 'P.DMG +2.5%']."""
    import datagame
    hasil = []
    for a, v in refine_per_level(item_id):
        if a in ATTR_REFINE:
            hasil.append(f"{ATTR_REFINE[a]} +{datagame._angka(float(v * refine))}")
        else:
            hasil.append(datagame.format_stat(a, v * refine))
    return hasil


# Id stat khusus refine yang tidak ada di daftar atribut roworlddb (arti dari tafsiran komunitas, belum pasti).
ATTR_REFINE = {29: "ATK (refine)", 32: "M.ATK (refine)", 35: "DEF (refine)", 38: "M.DEF (refine)",
               310: "Damage tambahan tetap", 312: "P.DMG tambahan tetap", 314: "M.DMG tambahan tetap"}


def pet(nama: str) -> dict | None:
    import datagame
    q = datagame._norm(nama)
    terbaik = max(muat("pet.json"), key=lambda p: datagame.skor_nama(q, p["nama"]), default=None)
    return terbaik if terbaik and datagame.skor_nama(q, terbaik["nama"]) >= 0.8 else None


def cari_tambahan(q_norm: str, jenis: str = "") -> list[dict]:
    """Cari di rune, pet, apocalypse, dan stunt/affix. Format sama dengan datagame.cari()."""
    import datagame
    hasil = []

    def cek(j: str, nama: str, data):
        s = datagame.skor_nama(q_norm, nama)
        if s >= 0.45:
            hasil.append({"jenis": j, "nama": nama, "skor": s, "data": data})

    if jenis in ("", "rune"):
        for nama, d in (muat("rune.json").get("efek") or {}).items():
            cek("rune", nama, d)
    if jenis in ("", "pet"):
        for p in muat("pet.json") or []:
            cek("pet", p["nama"], p)
    if jenis in ("", "apocalypse", "apoc"):
        for a in muat("apocalypse.json") or []:
            label = f"{a.get('judul') or a.get('kunci') or '?'}"
            cek("apocalypse", label, a)
    if jenis in ("", "affix", "stunt"):
        for st in muat("stunt.json") or []:
            label = f"{st['nama']} ({st['warna']})"
            s = max(datagame.skor_nama(q_norm, st["nama"]), datagame.skor_nama(q_norm, label))
            if s >= 0.45:
                hasil.append({"jenis": "affix", "nama": label, "skor": s, "data": st})
    return hasil


def teks_tambahan(h: dict) -> list[str]:
    j, d = h["jenis"], h["data"]
    if j == "rune":
        baris = [f"{h['nama']} - Rune ({d.get('elemen') or '?'})"]
        lvs = sorted((d.get("level") or {}).items(), key=lambda kv: int(kv[0]))
        for lv, desc in (lvs[:2] + (lvs[-1:] if len(lvs) > 2 else [])):
            baris.append(f"Lv.{lv}: {_bersih(desc)}")
        return baris
    if j == "pet":
        baris = [f"{d['nama']} - Pet ({d.get('kualitas') or '?'})"]
        lvs = [l for l in (d.get("level") or []) if _bersih(l.get("efek"))]
        for l in (lvs[:1] + (lvs[-1:] if len(lvs) > 1 else [])):
            baris.append(f"Bond Lv.{l['lv']} ({l.get('judul') or ''}): {_bersih(l.get('efek'))}")
        return baris
    if j == "apocalypse":
        baris = [f"{d.get('judul') or d.get('kunci')} - Apocalypse ({d.get('kualitas') or '?'})"]
        if d.get("slot"):
            slots = [x.get("name") or str(x) if isinstance(x, dict) else str(x) for x in d["slot"]]
            baris.append("Slot: " + ", ".join(slots))
        if d.get("job"):
            jobs = [x.get("name") or x.get("label") or str(x) if isinstance(x, dict) else str(x) for x in d["job"]]
            baris.append("Job: " + ", ".join(jobs[:6]) + (" ..." if len(jobs) > 6 else ""))
        baris.append("Efek: " + _bersih(d.get("efek")))
        return baris
    if j == "affix":
        baris = [f"{d['nama']} - Affix / Special Skill ({d['warna']})"]
        for lv, desc in sorted((d.get("level") or {}).items(), key=lambda kv: int(kv[0])):
            baris.append(f"Lv.{lv}: {desc}")
        return baris
    return []


if __name__ == "__main__":
    import sys
    if "--stunt" in sys.argv:
        perbarui_stunt()
    else:
        perbarui()
