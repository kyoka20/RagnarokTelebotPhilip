"""Data monster server SEA: ras, ukuran, elemen, DEF/M.DEF, HP (untuk sasaran test & bongkar rumus damage).

Sumber: rtnw.online (ekspor data client SEA buatan komunitas, BUKAN resmi Gravity).
Disimpan di database_tetap/monster.json. Folder ini TIDAK diganti saat database roworlddb diperbarui,
dan boleh dikirim lewat /update. Perbarui datanya: jalankan `python monster.py` (butuh internet).
"""
from __future__ import annotations

import json
import time
from datetime import datetime

import umum

SITUS = "https://rtnw.online"
BAHASA = "en-US"
FILE = umum.FOLDER / "database_tetap" / "monster.json"
HEADER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ROPython-database/1.0"}
# Sasaran Damage Challenge di data client tidak punya angka stat; dummy test lain (level & seri id sama)
# punya angka ini, jadi dipakai sebagai PERKIRAAN.
CADANGAN_STAT = {"Damage Test Dummy (Humanoid, Medium)": "DMG Test Dummy"}
_cache: dict = {}


def _ringkas(m: dict) -> dict:
    s = m.get("stats") or {}
    return {"id": m["id"], "nama": m["name"], "lv": m.get("level"), "tipe": (m.get("type") or {}).get("name"),
            "ras": (m.get("race") or {}).get("name"), "ukuran": (m.get("body") or {}).get("name"),
            "elemen": (m.get("element") or {}).get("name"),
            "hp": s.get("hp"), "def": s.get("pdef"), "mdef": s.get("mdef"), "flee": s.get("flee"),
            "crit_def": s.get("critDef")}


def perbarui(log=print) -> int:
    """Unduh ulang semua monster dari rtnw.online -> database_tetap/monster.json. Hasil: jumlah monster."""
    import requests
    sesi = requests.Session()
    dasar = f"{SITUS}/sea/monster-album/data"
    index = sesi.get(f"{dasar}/monster_index_{BAHASA}.json", headers=HEADER, timeout=60).json()
    semua = []
    for c in sorted({m["_detailChunk"] for m in index["monsters"]}):
        r = sesi.get(f"{dasar}/optimized/{BAHASA}/{c}", headers=HEADER, timeout=60)
        r.raise_for_status()
        semua += [_ringkas(m) for m in r.json()["monsters"] if m.get("name")]
        time.sleep(0.2)  # sopan ke server situs
    FILE.parent.mkdir(exist_ok=True)
    isi = {"sumber": SITUS + "/sea/monster-album/", "diunduh": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "monster": semua}
    FILE.write_text(json.dumps(isi, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _cache.clear()
    log(f"{len(semua)} monster tersimpan di {FILE}")
    return len(semua)


def semua() -> list[dict]:
    if "m" not in _cache:
        try:
            _cache["m"] = json.loads(FILE.read_text(encoding="utf-8"))["monster"]
        except (OSError, ValueError, KeyError):
            _cache["m"] = []
    return _cache["m"]


def cari(nama: str) -> dict | None:
    """Monster dengan nama paling mirip (salah ketik tidak apa-apa). Kembar nama -> yang punya angka stat."""
    import datagame
    q = datagame._norm(nama)
    terbaik, skor = None, 0.0
    for m in semua():
        s = datagame.skor_nama(q, m["nama"]) + (0.001 if m.get("def") is not None else 0)
        if s > skor:
            terbaik, skor = m, s
    return terbaik if skor >= 0.8 else None


def stat_sasaran(nama: str) -> tuple[dict | None, str | None]:
    """(monster, nama monster asal angka DEF kalau itu perkiraan)."""
    m = cari(nama)
    if not m:
        return None, None
    if m.get("def") is None and m["nama"] in CADANGAN_STAT:
        c = cari(CADANGAN_STAT[m["nama"]])
        if c and c.get("def") is not None:
            m = dict(m, **{k: c[k] for k in ("hp", "def", "mdef", "flee", "crit_def")})
            return m, c["nama"]
    return m, None


def teks_stat(nama: str) -> str | None:
    """Satu baris untuk laporan: DEF & M.DEF sasaran."""
    m, asal = stat_sasaran(nama)
    if not m or m.get("def") is None:
        return None
    t = f"DEF {m['def']} | M.DEF {m['mdef']} (data client"
    return t + (f", perkiraan dari {asal})" if asal else ")")


if __name__ == "__main__":
    perbarui()
