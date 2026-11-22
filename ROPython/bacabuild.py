"""Membaca halaman build dari layar game (HANYA screenshot + OCR, tidak menyentuh game).

Langkah 1: halaman Character Info > Detailed Stats.
Setiap kali halaman itu terbuka (dan di-scroll), angka-angkanya dikumpulkan, lalu disimpan
per karakter di data/<profil>/status_log.jsonl. Laporan DPS memakai ini untuk menunjukkan
stat apa yang berubah sejak test sebelumnya.
"""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from datetime import datetime

from PIL import Image

import catatan
import ocr

# Nama stat di halaman Detailed Stats (nama lengkap; di layar sering terpotong).
STAT = """
Max HP|Max SP|ATK|DEF|M.ATK|M.DEF|HIT|FLEE|Attack Frequency|ASPD|CRIT|CRIT RES
CRIT DMG%|CRIT DMG RES%|Variable Cast Time|Variable Cast Time%|Fixed Cast Time|Fixed Cast Time%
HP Recovery|SP Recovery|PDMG Bonus%|PDMG Reduction%|MDMG Bonus%|MDMG Reduction%
Melee PDMG%|Melee PDMG Reduction%|Ranged PDMG%|Ranged PDMG Reduction%
Melee MDMG%|Melee MDMG Reduction%|Ranged MDMG%|Ranged MDMG Reduction%
Ignore P.DEF|Ignore P.DEF%|Ignore M.DEF|Ignore M.DEF%|Normal Attack DMG%|Skill DMG%
PVP DMG%|PVP DMG Reduction%|Royal Might DMG%|Royal Might DMG Reduction%|Aggressive|Defensive
Apocalypse DMG%|Apocalypse DMG Reduction%|MSPD|Fixed DMG|Fixed DMG Reduction
Freeze Boost|Freeze RES|Petrify Boost|Petrify RES|Stun Boost|Stun RES|Root Boost|Root RES
Blind Boost|Blind RES|Silence Boost|Silence RES|Sleep Boost|Sleep RES|Knockback Boost|Knockback RES
Confuse Boost|Confuse RES|ATK%|M.ATK%|Healing%|Received Healing%
DMG vs Small%|DMG vs Medium%|DMG vs Large%|DMG Reduction vs Small%|DMG Reduction vs Medium%|DMG Reduction vs Large%
DMG vs Human%|DMG vs Brute%|DMG vs Demon%|DMG vs Undead Race%|DMG vs Formless%|DMG vs Fish%|DMG vs Angel%
DMG vs Insect%|DMG vs Mech%|DMG vs Plant%|DMG vs Dragon%|DMG vs Demi-Human%
DMG Reduction vs Human%|DMG Reduction vs Demi-Human%|DMG Reduction vs Brute%|DMG Reduction vs Demon%
DMG Reduction vs Undead Race%|DMG Reduction vs Formless%|DMG Reduction vs Fish%|DMG Reduction vs Angel%
DMG Reduction vs Insect%|DMG Reduction vs Mech%|DMG Reduction vs Plant%|DMG Reduction vs Dragon%
Elemental DMG%|Elemental DMG Reduction%
Neutral DMG%|Water DMG%|Earth DMG%|Fire DMG%|Wind DMG%|Poison DMG%|Holy DMG%|Shadow DMG%|Ghost DMG%|Undead DMG%
Neutral DMG Reduction%|Water DMG Reduction%|Earth DMG Reduction%|Fire DMG Reduction%|Wind DMG Reduction%
Poison DMG Reduction%|Holy DMG Reduction%|Shadow DMG Reduction%|Ghost DMG Reduction%|Undead DMG Reduction%
DMG vs Neutral%|DMG vs Water%|DMG vs Earth%|DMG vs Fire%|DMG vs Wind%|DMG vs Poison%|DMG vs Holy%
DMG vs Shadow%|DMG vs Ghost%|DMG vs Undead%
Neutral RES|Water RES|Earth RES|Fire RES|Wind RES|Poison RES|Holy RES|Shadow RES|Ghost RES|Undead RES
Final DMG|Final PDMG|Final MDMG|Final DMG Reduction|Final PDMG Reduction|Final MDMG Reduction
""".replace("\n", "|").split("|")
STAT = [s.strip() for s in STAT if s.strip()]

# Urutan penting untuk DPS (ditampilkan duluan di laporan perubahan)
PENTING = ["ATK", "ATK%", "M.ATK", "M.ATK%", "PDMG Bonus%", "MDMG Bonus%", "Melee PDMG%", "Ranged PDMG%",
           "Skill DMG%", "Normal Attack DMG%", "Final PDMG", "Final MDMG", "Final DMG",
           "CRIT", "CRIT DMG%", "Ignore P.DEF", "Ignore P.DEF%", "Ignore M.DEF", "Ignore M.DEF%",
           "Elemental DMG%", "Neutral DMG%", "Attack Frequency", "ASPD",
           "Variable Cast Time%", "Fixed Cast Time%", "Fixed DMG",
           "Royal Might DMG%", "Apocalypse DMG%", "Aggressive"]

_NILAI = re.compile(r"^[-+¯]?\d[\d.,]*(%|0/6|0/0|O/O|o/o|/6|/0|/)?$")
_KATA_JUDUL = re.compile(r"Base Stats|Other Attributes|Control Attribute|Specials|DMG vs|Final DMG|"
                         r"Detailed|iled Stat|ed Stats|CRIT RES|Max HP", re.I)


def halaman_status(teks: str) -> bool:
    """True kalau teks layar (OCR) menunjukkan halaman Character Info > Detailed Stats."""
    return "Character Info" in teks and bool(_KATA_JUDUL.search(teks))


def _nilai(t: str) -> str | None:
    t = t.replace("¯", "-").strip()
    if t in ("o", "O"):
        return "0"
    if t in ("I", "l", "|"):  # angka 1 sering terbaca huruf I / l
        return "1"
    if not _NILAI.match(t):
        return None
    for akhir in ("0/6", "0/0", "O/O", "o/o", "/6", "/0", "/", "%"):
        if t.endswith(akhir):
            angka = t[: -len(akhir)] or "0"
            return angka.rstrip(".,") + "%"
    return t


def _kunci(t: str) -> str:
    return re.sub(r"[^a-z0-9%]", "", t.lower())


_KUNCI_STAT = {s: _kunci(s) for s in STAT}


def nama_resmi(label: str, nilai: str) -> str | None:
    """Label di layar (sering terpotong / salah baca) -> nama stat lengkap. None kalau tidak yakin."""
    k = _kunci(label)
    if len(k) < 3:
        return None
    calon = [s for s, ks in _KUNCI_STAT.items() if k in ks]
    if not calon:
        skor = sorted(((difflib.SequenceMatcher(None, k, ks).ratio(), s) for s, ks in _KUNCI_STAT.items()), reverse=True)
        if skor[0][0] < 0.72:
            return None
        calon = [s for r, s in skor if r >= skor[0][0] - 0.02]
    # Angka ber-% hanya untuk stat ber-%, dan sebaliknya (OCR kadang membuang % dari label).
    persen = nilai.endswith("%")
    calon = [s for s in calon if s.endswith("%") == persen]
    if len(calon) > 1:
        sama = [s for s in calon if _KUNCI_STAT[s] in (k, k + "%", k.rstrip("%"))]
        # Masih lebih dari satu (mis. "Cast Time" = Variable atau Fixed?) -> jangan menebak.
        return sama[0] if len(sama) == 1 else None
    return calon[0] if calon else None


def baca_status(img: Image.Image, cfg_ocr: dict) -> dict[str, str]:
    """Baca semua pasangan (stat, angka) yang terlihat di halaman Detailed Stats."""
    W, H = img.size
    panel = img.crop((int(W * 0.55), 0, W, H))
    skala = max(1.0, 1300 / panel.width)
    if skala > 1:
        panel = panel.resize((int(panel.width * skala), int(panel.height * skala)), Image.LANCZOS)
    kata, _ = ocr._jalankan_mesin(panel, cfg_ocr)
    hasil: dict[str, str] = {}
    for baris in ocr._kelompokkan_baris(kata):
        label: list[str] = []
        for k in baris:  # kiri -> kanan: kata-kata lalu angka = satu pasangan (1 atau 2 kolom)
            v = _nilai(k.teks) if label else None
            if v is not None:
                nama = nama_resmi(" ".join(label), v)
                if nama:
                    hasil.setdefault(nama, v)
                label = []
            else:
                label.append(k.teks)
    return hasil


def angka_float(v: str) -> float | None:
    try:
        return float(v.rstrip("%").replace(",", ""))
    except ValueError:
        return None


class Pengumpul:
    """Kumpulkan bacaan dari beberapa frame (scroll) jadi satu; tiap stat pakai bacaan terbanyak."""

    def __init__(self):
        self.suara: dict[str, Counter] = {}
        self.terakhir = None

    def tambah(self, data: dict[str, str]) -> None:
        for k, v in data.items():
            self.suara.setdefault(k, Counter())[v] += 1
        self.terakhir = datetime.now()

    def hasil(self) -> dict[str, str]:
        return {k: c.most_common(1)[0][0] for k, c in self.suara.items()}


# ------------------------------------------------------------ simpan / bandingkan

def _file_log(pid: str):
    return catatan.folder_profil(pid) / "status_log.jsonl"


def simpan(pid: str, status: dict[str, str], waktu: datetime) -> None:
    if not status:
        return
    with _file_log(pid).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"waktu": waktu.strftime(catatan.FORMAT_WAKTU), "status": status},
                            ensure_ascii=False) + "\n")


def baca_log(pid: str) -> list[tuple[datetime, dict[str, str]]]:
    f = _file_log(pid)
    if not f.exists():
        return []
    hasil = []
    for baris in f.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(baris)
            hasil.append((datetime.strptime(d["waktu"], catatan.FORMAT_WAKTU), d["status"]))
        except (ValueError, KeyError):
            continue
    return hasil


def _sebelum(log, batas: datetime):
    """Gabungan semua bacaan sampai waktu `batas` (bacaan baru menimpa yang lama)."""
    gabung, ada = {}, False
    for w, s in log:
        if w <= batas:
            gabung.update(s)
            ada = True
    return gabung if ada else None


def perubahan(pid: str, test_lalu: datetime | None, sekarang: datetime, tak_terpakai: set | None = None) -> list[str]:
    """Baris laporan: stat yang berubah antara test sebelumnya dan sekarang.
    Hanya kalau halaman Status dibuka setelah test sebelumnya.
    tak_terpakai = stat yang tidak berpengaruh ke sasaran test (ditandai di laporan)."""
    tak_terpakai = tak_terpakai or set()
    log = baca_log(pid)
    if not log or test_lalu is None:
        return []
    baru = [s for w, s in log if test_lalu < w <= sekarang]
    if not baru:
        return []
    lama = _sebelum(log, test_lalu)
    if lama is None:
        return ["📋 Stat karakter tersimpan (pembanding untuk test berikutnya)."]
    dilihat = {}
    for s in baru:
        dilihat.update(s)
    beda = []
    for k, v in dilihat.items():
        a, b = angka_float(lama.get(k, "")), angka_float(v)
        if a is None or b is None or abs(a - b) < 1e-9:
            continue
        beda.append((PENTING.index(k) if k in PENTING else 99, k, lama[k], v, b - a))
    if not beda:
        return ["📋 Stat yang terlihat di halaman Status sama dengan test sebelumnya."]
    beda.sort()
    teks = []
    for _, k, a, b, d in beda[:6]:
        tanda = "+" if d > 0 else ""
        selisih = f"{tanda}{d:.2f}".rstrip("0").rstrip(".") + ("%" if b.endswith("%") else "")
        teks.append(f"{k} {a} → {b} ({selisih})" + (" ⚪ tidak berpengaruh di test" if k in tak_terpakai else ""))
    lebih = f" (+{len(beda) - 6} lainnya)" if len(beda) > 6 else ""
    return ["🔧 <b>Stat berubah sejak test lalu</b>" + lebih + ":\n" + "\n".join("   " + t for t in teks)]
