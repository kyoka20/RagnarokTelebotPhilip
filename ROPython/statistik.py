"""Panel STATISTICS sesudah Damage Challenge: damage per skill + persentasenya (HANYA screenshot + OCR).

Philip menekan tombol "Statistics" (kanan bawah layar VICTORY); bot TIDAK mengklik apa pun.
Tiap baris panel: <nama skill> ... <damage> ... <persen%>. Dari sini bot tahu skill mana yang
menyumbang damage. Membandingkan 2 sumber damage dalam test yang SAMA membuat DEF musuh, crit, dan
bonus global saling coret (cara dari studi Sniper), jadi rumus bisa dibongkar tanpa menebak.

Tata letak panel belum pernah dilihat developer, jadi pembacaannya longgar, dan beberapa gambar
panel disimpan di data/<profil>/statistik/ supaya bisa dipelajari & dirapikan nanti.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime

from PIL import Image

import catatan
import ocr
import layar

_PERSEN = re.compile(r"^\(?(\d{1,3}(?:[.,]\d{1,2})?)\s*%\)?$")
_ANGKA = re.compile(r"^[\d.,]+[kKmMbB]?$")
TAMBAHAN = ["Basic Attack", "Normal Attack", "Auto Attack", "Pet", "Falcon", "Others", "Other"]


def _nama_skill() -> list[str]:
    try:
        import datagame
        nama = {s["nama"] for s in datagame._skill_semua()}
    except Exception:
        nama = set()
    return sorted(nama | set(TAMBAHAN))


_SKILL: list[str] | None = None


def cocok_skill(teks: str) -> str | None:
    """Nama di layar (OCR) -> nama skill resmi kalau cukup mirip."""
    global _SKILL
    if _SKILL is None:
        _SKILL = _nama_skill()
    import datagame
    q = datagame._norm(teks)
    if len(q) < 3:
        return None
    terbaik, skor = None, 0.0
    for n in _SKILL:
        s = datagame.skor_nama(q, n)
        if s > skor:
            terbaik, skor = n, s
    return terbaik if skor >= 0.85 else None


def halaman_statistik(teks: str) -> bool:
    """Teks layar menunjukkan panel statistik damage? (judul 'Statistic' + minimal 2 angka persen)."""
    t = teks or ""
    if "Detailed Stats" in t or "Set Effect" in t:
        return False
    persen = len(re.findall(r"\d\s*%", t))
    return persen >= 2 and re.search(r"statistic", t, re.I) is not None


def _angka(t: str) -> int | None:
    t = t.strip().replace(" ", "")
    if not _ANGKA.match(t):
        return None
    return ocr.parse_angka(t)


def baca(img: Image.Image, cfg_ocr: dict) -> list[dict]:
    """Baris {nama, dmg, persen} yang terlihat. nama = nama skill resmi kalau dikenali, selain itu teks mentah."""
    besar = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    kata, _ = ocr._jalankan_mesin(besar, cfg_ocr)
    hasil = []
    for b in ocr._kelompokkan_baris(kata):
        teks = [k.teks.strip() for k in b if k.teks.strip()]
        persen = dmg = None
        nama_kata = []
        for t in teks:
            m = _PERSEN.match(t)
            if m:
                persen = float(m.group(1).replace(",", "."))
                continue
            n = _angka(t)
            if n is not None and nama_kata:  # angka sesudah nama = damage (ambil yang terbesar)
                dmg = max(dmg or 0, n)
                continue
            if dmg is None and persen is None:
                nama_kata.append(t)
        if persen is None or not nama_kata or persen > 100:
            continue
        mentah = " ".join(nama_kata)
        hasil.append({"nama": cocok_skill(mentah) or mentah, "dikenal": cocok_skill(mentah) is not None,
                      "dmg": dmg, "persen": persen})
    return hasil


class Pengumpul:
    """Gabungkan bacaan beberapa frame (panel di-scroll / dibaca ulang); tiap skill pakai angka terbanyak."""

    def __init__(self):
        self.suara: dict[str, dict[str, Counter]] = {}
        self.urut: list[str] = []
        self.dikenal: dict[str, bool] = {}
        self.terakhir: datetime | None = None
        self.gambar: list[Image.Image] = []
        self.sidik = None

    def tambah(self, baris: list[dict], img: Image.Image | None = None) -> None:
        self.terakhir = datetime.now()
        for r in baris:
            n = r["nama"]
            if n not in self.suara:
                self.suara[n] = {"dmg": Counter(), "persen": Counter()}
                self.urut.append(n)
            self.dikenal[n] = self.dikenal.get(n, False) or r["dikenal"]
            if r["dmg"]:
                self.suara[n]["dmg"][r["dmg"]] += 1
            self.suara[n]["persen"][r["persen"]] += 1
        if img is not None and len(self.gambar) < 4:
            self.gambar.append(img.copy())

    def hasil(self) -> list[dict]:
        out = []
        for n in self.urut:
            s = self.suara[n]
            out.append({"nama": n, "dikenal": self.dikenal[n],
                        "dmg": s["dmg"].most_common(1)[0][0] if s["dmg"] else None,
                        "persen": s["persen"].most_common(1)[0][0]})
        return sorted(out, key=lambda r: -r["persen"])


def _folder(pid: str):
    f = catatan.folder_profil(pid) / "statistik"
    f.mkdir(exist_ok=True)
    return f


def simpan(pid: str, sumber: list[dict], waktu: datetime, test: dict | None, gambar: list[Image.Image]) -> dict:
    """Simpan ke data/<pid>/statistik.jsonl (+ gambar panel). Hasil: catatan yang disimpan."""
    jumlah = round(sum(r["persen"] for r in sumber), 1)
    total = (test or {}).get("total")
    for r in sumber:  # angka damage tidak terbaca -> perkiraan dari persen x Total DMG test itu
        if not r.get("dmg") and total:
            r["dmg"], r["dmg_perkiraan"] = round(total * r["persen"] / 100), True
    d = {"waktu": waktu.strftime(catatan.FORMAT_WAKTU), "test": test, "jumlah_persen": jumlah, "sumber": sumber}
    nama_gambar = []
    for i, g in enumerate(gambar):
        nm = f"{waktu:%Y%m%d_%H%M%S}_{i}.jpg"
        try:
            g.convert("RGB").save(_folder(pid) / nm, quality=88)
            nama_gambar.append(nm)
        except OSError:
            pass
    d["gambar"] = nama_gambar
    with (catatan.folder_profil(pid) / "statistik.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    return d


def baca_log(pid: str) -> list[dict]:
    f = catatan.folder_profil(pid) / "statistik.jsonl"
    if not f.exists():
        return []
    out = []
    for b in f.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(b))
        except ValueError:
            continue
    return out


def teks_laporan(d: dict, nama_akun: str) -> str:
    """Pesan Telegram singkat."""
    import html
    import umum
    t = d.get("test") or {}
    baris = [f"📊 <b>Damage per skill</b> - {html.escape(nama_akun)}"
             + (f" (test {t['waktu'][11:16]}, DPS {umum.fmt(t['dps'])})" if t.get("waktu") else "")]
    for r in d["sumber"][:10]:
        dmg = f" - {'±' if r.get('dmg_perkiraan') else ''}{umum.fmt(r['dmg'])}" if r.get("dmg") else ""
        tanda = "" if r.get("dikenal") else " ❓"
        baris.append(f"• {html.escape(r['nama'])}{tanda}: <b>{r['persen']:g}%</b>{dmg}")
    j = d["jumlah_persen"]
    if abs(j - 100) > 3:
        baris.append(f"⚠️ Jumlah persen {j:g}% (bukan ±100%): mungkin ada baris yang belum terbaca, "
                     f"coba scroll panelnya.")
    return "\n".join(baris)


def sidik_beda(lama, img) -> tuple[bool, object]:
    """(layar berubah?, sidik baru)."""
    s = layar.sidik(img)
    return lama is None or layar.beda(lama, s) >= 1.0, s
