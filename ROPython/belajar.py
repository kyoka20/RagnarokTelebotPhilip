"""Belajar OTOMATIS dari halaman Enchant di game (hanya screenshot + OCR, tidak menyentuh game).

Yang dibaca dari layar:
  • Detail gem (tekan lama ikon gem):  nama gem, "Gem Stats" (angka di level gem itu),
    dan kalimat "Can be enchanted into ..." (slot yang boleh + stat dasar).
  • "Set Effect: <nama set> Lv.N" di bawah panel enchant: efek set di level itu.

Hasil disimpan di database_lokal/enchant_belajar.json (tiap bacaan = 1 suara, yang terbanyak dipakai),
lalu ikut tampil di /db dan dipakai saran. Tidak perlu Claude lagi untuk mempelajarinya.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
from collections import Counter
from datetime import datetime

from PIL import Image

import ocr
import umum

FILE_BELAJAR = umum.FOLDER / "database_lokal" / "enchant_belajar.json"
_kunci_file = threading.Lock()

SLOT = {"weapon": "Weapon", "accessor": "Accessory", "off-hand": "Off-Hand", "offhand": "Off-Hand", "shoe": "Shoes",
        "cape": "Cape", "armor": "Armor", "headwear": "Headwear", "backwear": "Backwear", "facewear": "Facewear",
        "mouthwear": "Mouthwear"}

STAT_DASAR = ["STR", "AGI", "VIT", "INT", "DEX", "LUK", "HP", "SP", "Max HP", "Max SP", "ATK", "M.ATK", "P.ATK%",
              "DEF", "P.DEF", "M.DEF", "HIT", "FLEE", "CRIT", "CRIT RES", "ASPD", "ATK%", "M.ATK%", "PDMG Bonus%",
              "PDMG Boost%", "MDMG Bonus%", "Fixed Bonus DMG", "Final DMG", "Elemental DMG%", "Base HP Recovery",
              "Base SP Recovery", "HP Recovery", "SP Recovery", "Healing%", "Skill DMG%", "CRIT DMG%"]


# ------------------------------------------------------------ bantu teks

def _rapikan_angka(t: str) -> str:
    return t.translate(str.maketrans({"I": "1", "l": "1", "|": "1", "O": "0", "o": "0", ",": "."}))


def _daftar_stat() -> list[str]:
    try:
        import bacabuild
        return list(dict.fromkeys(STAT_DASAR + bacabuild.STAT))
    except Exception:
        return STAT_DASAR


_STAT = None


def nama_stat(label: str) -> str:
    """Label stat hasil OCR -> nama baku (kalau mirip), selain itu label yang dirapikan."""
    global _STAT
    if _STAT is None:
        _STAT = {re.sub(r"[^a-z0-9%]", "", s.lower()): s for s in _daftar_stat()}
    label = re.sub(r"\s+", " ", label).strip(" .:*+-")
    k = re.sub(r"[^a-z0-9%]", "", label.lower())
    if k in _STAT:
        return _STAT[k]
    cocok = difflib.get_close_matches(k, list(_STAT), n=1, cutoff=0.8)
    return _STAT[cocok[0]] if cocok else label


# "+ ATK+10", "HP+300", "Elemental DMG%+1%", "Fixed Bonus DMG +10", "Hp.600", "FLEE* 1"
_POLA_STAT = re.compile(r"([A-Za-z][A-Za-z .%'/-]*?)\s*[+*.]\s*([0-9IlOo|][0-9IlOo|.,]*)\s*(%?)\s*$")


def baca_stat(t: str) -> str | None:
    t = re.sub(r"[0Oo]/[0Oo]", "%", t)  # "%" sering terbaca "0/O"
    t = re.sub(r"\+i\b", "+1", t)
    t = t.strip().lstrip("+*✦◆•·@ ").strip()
    m = _POLA_STAT.search(t)
    if not m:
        return None
    angka = _rapikan_angka(m.group(2)).strip(".")
    if not re.fullmatch(r"\d+(\.\d+)?", angka):
        return None
    nama = nama_stat(m.group(1))
    if len(re.sub(r"[^A-Za-z]", "", nama)) < 2:
        return None
    return f"{nama} +{angka}{m.group(3)}"


def _romawi(t: str) -> str:
    """'Frenzy Ill' -> 'Frenzy III', 'Fortitude l' -> 'Fortitude I'."""
    kata = t.split()
    if kata and re.fullmatch(r"[IVl1|]+", kata[-1]):
        kata[-1] = kata[-1].replace("l", "I").replace("1", "I").replace("|", "I")
    return " ".join(kata)


def _nama_set_dikenal() -> list[str]:
    import datagame
    return list(datagame.enchant_lokal(gabung=False).get("set", {}))


def _nama_gem_dikenal() -> list[str]:
    import datagame
    nama = list(datagame.enchant_lokal(gabung=False).get("gem", {}))
    try:
        nama += [g["name"] for g in datagame._muat("gem.json")]
    except Exception:
        pass
    return list(dict.fromkeys(nama))


def cocokkan(teks: str, daftar: list[str], batas: float = 0.82) -> str | None:
    if not teks:
        return None
    k = teks.lower().replace(" ", "")
    peta = {n.lower().replace(" ", ""): n for n in daftar}
    if k in peta:
        return peta[k]
    c = difflib.get_close_matches(k, list(peta), n=1, cutoff=batas)
    return peta[c[0]] if c else None


# ------------------------------------------------------------ baca layar

def _ocr(img: Image.Image, cfg_ocr: dict, skala: float = 2.0) -> list[list[ocr.Kata]]:
    if skala != 1:
        img = img.resize((max(1, int(img.width * skala)), max(1, int(img.height * skala))), Image.LANCZOS)
    kata, _ = ocr._jalankan_mesin(img, cfg_ocr)
    return ocr._kelompokkan_baris(kata)


def _baca_stat_varian(potong: Image.Image, cfg_ocr: dict) -> list[str]:
    """Baris stat di potongan layar. Teks berwarna (oranye/hijau) sering salah baca, jadi dibaca
    beberapa cara (diperbesar 2x, 3x, hitam-putih) dan tiap stat diambil angka yang paling sering muncul."""
    from PIL import ImageOps
    varian = [(potong, 2.0), (potong, 3.0), (ImageOps.autocontrast(potong.convert("L")).convert("RGB"), 2.5)]
    urutan, suara = [], {}
    for gb, sk in varian:
        for b in _ocr(gb, cfg_ocr, sk):
            s = baca_stat(_baris_teks(b))
            if not s:
                continue
            nama, nilai = s.rsplit(" +", 1)
            if nama not in suara:
                urutan.append(nama)
            suara.setdefault(nama, Counter())[nilai] += 1
    hasil = []
    for nama in urutan:
        nilai, n = suara[nama].most_common(1)[0]
        if n >= 2 or sum(suara[nama].values()) >= 2:
            hasil.append(f"{nama} +{nilai}")
    return hasil


def _baris_teks(b: list[ocr.Kata]) -> str:
    return " ".join(k.teks for k in b)


def _cari_kata(baris, *urutan: str):
    """Cari kata-kata berurutan (awalan, tidak peka huruf besar) di satu baris. Hasil: (kata pertama, kata terakhir)."""
    for b in baris:
        for i in range(len(b) - len(urutan) + 1):
            if all(b[i + j].teks.lower().startswith(u.lower()) for j, u in enumerate(urutan)):
                return b[i], b[i + len(urutan) - 1]
    return None


def _potong(img, x0, y0, x1, y1):
    W, H = img.size
    return img.crop((max(0, int(x0)), max(0, int(y0)), min(W, int(x1)), min(H, int(y1))))


def baca_set(img: Image.Image, baris, cfg_ocr: dict) -> dict | None:
    """'Set Effect: Frenzy III Lv.1' + baris stat di bawahnya."""
    k = _cari_kata(baris, "Set", "Effect") or _cari_kata(baris, "Effect:")
    if not k:
        return None
    a, _ = k
    h = max(a.h, 8)
    # Judul (diperbesar supaya "Lv.1" terbaca)
    judul = " ".join(_baris_teks(b) for b in _ocr(_potong(img, a.x - h * 0.5, a.y - h * 0.4, a.x + h * 17, a.y + h * 1.4), cfg_ocr))
    if "not activ" in judul.lower():
        return None
    m = re.search(r"Effect\s*:?\s*(.+?)(?:\s+L[v'.,]\S*?\s*([0-9Il|]{1,2})?\s*$|\s*$)", judul)
    if not m:
        return None
    mentah = _romawi(re.sub(r"\s+L[v'.,]?\S*$", "", m.group(1)).strip(" .:"))
    nama = cocokkan(mentah, _nama_set_dikenal())
    lv = _rapikan_angka(m.group(2) or "")
    level = int(lv) if lv.isdigit() else None
    efek = _baca_stat_varian(_potong(img, a.x - h * 0.8, a.y + h * 1.1, a.x + h * 13, a.y + h * 9), cfg_ocr)
    return {"nama": nama, "nama_terbaca": mentah, "level": level, "efek": efek}


def baca_gem(img: Image.Image, baris, cfg_ocr: dict) -> dict | None:
    """Kotak detail gem: judul (nama), 'Gem Stats:' + angka, 'Can be enchanted into ...'."""
    k = _cari_kata(baris, "Gem", "Stats")
    if not k:
        return None
    a, _ = k
    h = max(a.h, 8)
    # Judul gem ada di atas sub-judul "Enchant Stone" pada kolom yang sama.
    sub = None
    for b in baris:
        for i in range(len(b) - 1):
            if b[i].teks.lower() == "enchant" and b[i + 1].teks.lower().startswith("stone") \
                    and b[i].y < a.y and abs(b[i].x - a.x) < h * 3:
                sub = b[i]
    nama = None
    if sub is not None:
        dikenal = _nama_gem_dikenal()
        # 1) judul yang sudah terbaca di OCR layar penuh (baris tepat di atas "Enchant Stone", kolom sama)
        calon = [" ".join(k.teks for k in b if sub.x - h <= k.x <= sub.x + h * 14) for b in baris
                 if sub.y - h * 3.5 < b[0].y + 0 < sub.y - h * 0.3 or any(sub.y - h * 3.5 < k.y < sub.y - h * 0.3 for k in b)]
        # 2) potongan diperbesar
        calon.append(" ".join(_baris_teks(b) for b in _ocr(_potong(img, sub.x - h * 0.5, sub.y - h * 3.2, sub.x + h * 15, sub.y - h * 0.1), cfg_ocr)))
        for judul in calon:
            judul = judul.strip()
            nama = cocokkan(judul, dikenal, 0.75)
            if nama:
                break
        if not nama:
            for judul in calon:
                if re.fullmatch(r"[A-Z][A-Za-z' ]{2,30}", judul.strip()) and "enchant" not in judul.lower():
                    nama = judul.strip()
                    break
    # Isi kotak: dari "Gem Stats" ke bawah sampai sebelum "An ore ..." / "How to Obtain"
    isi = [_baris_teks(b) for b in _ocr(_potong(img, a.x - h * 1.5, a.y + h * 0.9, a.x + h * 19, a.y + h * 9), cfg_ocr)]
    stat, desk = [], []
    for t in isi:
        if re.search(r"An ore|How to Obtain|imbued", t, re.I):
            break
        if desk or re.search(r"can be enchant", t, re.I):
            desk.append(t)
        else:
            s = baca_stat(t)
            if s:
                stat.append(s)
    deskripsi = re.sub(r"\s+", " ", " ".join(desk)).strip()
    slot = [v for kk, v in SLOT.items() if kk in deskripsi.lower()]
    slot = list(dict.fromkeys(slot))
    dasar = baca_stat(deskripsi.split(",")[-1]) if deskripsi else None
    if not nama or not (stat or deskripsi):
        return None
    return {"nama": nama, "stat": stat, "deskripsi": deskripsi, "slot": slot, "stat_dasar": dasar}


def baca_halaman(img: Image.Image, cfg_ocr: dict, baris=None) -> dict:
    """Baca satu gambar halaman Enchant. Hasil: {'set': {...}?, 'gem': {...}?}."""
    img = img.convert("RGB")
    if baris is None:
        baris = _ocr(img, cfg_ocr, 1.0)
    hasil = {}
    try:
        s = baca_set(img, baris, cfg_ocr)
        if s and s["efek"] and s["level"]:
            hasil["set"] = s
    except Exception:
        pass
    try:
        g = baca_gem(img, baris, cfg_ocr)
        if g:
            hasil["gem"] = g
    except Exception:
        pass
    return hasil


def ada_enchant(teks: str) -> bool:
    return bool(re.search(r"Set Effect|Gem Stats|Enchant Stone", teks))


# ------------------------------------------------------------ simpan

def muat() -> dict:
    try:
        return json.loads(FILE_BELAJAR.read_text(encoding="utf-8"))
    except Exception:
        return {"set": {}, "gem": {}}


def _pilih(suara: dict) -> str:
    return max(suara.items(), key=lambda kv: kv[1])[0]


def simpan(bacaan: list[dict]) -> list[str]:
    """Gabungkan bacaan ke file belajar. Hasil: baris laporan hal BARU / BERUBAH (untuk Telegram)."""
    if not bacaan:
        return []
    with _kunci_file:
        db = muat()
        db.setdefault("set", {})
        db.setdefault("gem", {})
        sebelum = _rapi(db)
        waktu = datetime.now().strftime("%Y-%m-%d %H:%M")
        for b in bacaan:
            s = b.get("set")
            if s and s.get("nama") and s.get("level"):
                d = db["set"].setdefault(s["nama"], {"level": {}})
                lv = d["level"].setdefault(str(s["level"]), {"n": 0, "stat": {}})
                lv["n"] += 1
                for e in s["efek"]:  # tiap stat dihitung sendiri (kadang satu baris tidak terbaca)
                    nama, nilai = e.rsplit(" +", 1)
                    v = lv["stat"].setdefault(nama, {})
                    v[nilai] = v.get(nilai, 0) + 1
                d["terakhir"] = waktu
            g = b.get("gem")
            if g:
                d = db["gem"].setdefault(g["nama"], {})
                for bagian in ("stat", "deskripsi", "slot", "stat_dasar"):
                    nilai = g.get(bagian)
                    if not nilai:
                        continue
                    kunci = json.dumps(nilai, ensure_ascii=False)
                    suara = d.setdefault(bagian, {})
                    suara[kunci] = suara.get(kunci, 0) + 1
                d["terakhir"] = waktu
        FILE_BELAJAR.parent.mkdir(parents=True, exist_ok=True)
        FILE_BELAJAR.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    return _laporan(sebelum, _rapi(db))


def _efek_level(lv: dict) -> str:
    """Stat yang muncul di cukup banyak bacaan (buang salah baca sekali-sekali), angka terbanyak."""
    n = lv.get("n", 1)
    batas = 1 if n <= 2 else max(2, round(n * 0.3))
    efek = [f"{nama} +{_pilih(v)}" for nama, v in lv.get("stat", {}).items() if sum(v.values()) >= batas]
    return ", ".join(efek)


def _rapi(db: dict) -> dict:
    hasil = {"set": {}, "gem": {}}
    for nama, d in db.get("set", {}).items():
        hasil["set"][nama] = {lv: _efek_level(x) for lv, x in d.get("level", {}).items() if isinstance(x, dict) and x.get("stat")}
    for nama, d in db.get("gem", {}).items():
        hasil["gem"][nama] = {k: json.loads(_pilih(d[k])) for k in ("stat", "deskripsi", "slot", "stat_dasar") if d.get(k)}
    return hasil


def _laporan(lama: dict, baru: dict) -> list[str]:
    out = []
    for nama, lvs in baru.get("set", {}).items():
        for lv, efek in sorted(lvs.items(), key=lambda kv: int(kv[0])):
            if efek and lama.get("set", {}).get(nama, {}).get(lv) != efek:
                out.append(f"✨ Set {nama} Lv.{lv}: {efek}")
    for nama, d in baru.get("gem", {}).items():
        dl = lama.get("gem", {}).get(nama, {})
        bagian = []
        if d.get("stat_dasar") and dl.get("stat_dasar") != d["stat_dasar"]:
            bagian.append("dasar " + d["stat_dasar"])
        if d.get("slot") and dl.get("slot") != d["slot"]:
            bagian.append("slot " + ", ".join(d["slot"]))
        if d.get("stat") and dl.get("stat") != d["stat"]:
            bagian.append("terlihat " + ", ".join(d["stat"]))
        if bagian:
            out.append(f"💎 {nama}: " + "; ".join(bagian))
    return out


def ringkas() -> dict:
    """Versi rapi untuk digabung ke database enchant: {'set': {nama: {lv: 'efek'}}, 'gem': {nama: {...}}}."""
    return _rapi(muat())


class Pengamat:
    """Dipakai bot saat memantau: tiap kali halaman Enchant terlihat (dan layarnya berubah), baca & pelajari."""

    def __init__(self):
        self.sidik = None
        self.terakhir: dict = {}  # bacaan terakhir (untuk dicatat per karakter)

    def lihat(self, img, teks: str, cfg_ocr: dict) -> list[str]:
        import layar
        self.terakhir = {}
        if img is None or not ada_enchant(teks):
            return []
        s = layar.sidik(img)
        if self.sidik is not None and layar.beda(self.sidik, s) < 1.0:
            return []
        self.sidik = s
        b = baca_halaman(img, cfg_ocr)
        self.terakhir = b
        return simpan([b]) if b else []


if __name__ == "__main__":  # uji: python belajar.py gambar1.jpg gambar2.jpg ...
    import sys
    umum.siapkan_konsol()
    cfg = umum.muat_config()["ocr"]
    for f in sys.argv[1:]:
        print(f, json.dumps(baca_halaman(Image.open(f), cfg), ensure_ascii=False))
