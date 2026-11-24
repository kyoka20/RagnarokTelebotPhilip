"""Sambungan Gemini API (Google, versi gratis) untuk bot Ragnarok Philip.

100% on-demand (hanya dipanggil saat pengguna menjalankan /tanya atau /analisis).
Tidak membebani CPU/RAM laptop Philip, dan tidak butuh paket tambahan (memakai requests).

API key disimpan di config.json bagian "gemini": {"api_key": "...", "model": "..."}
lewat perintah /gemini_key <API_KEY> (pesan key langsung dihapus dari chat Telegram).
"""
from __future__ import annotations

import base64
import html
import json
import logging
import re
import subprocess
import time
from typing import Any

import requests

import bacabuild
import catatan
import rumus
import statistik
import umum

MODEL_BAWAAN = "gemini-flash-latest"
MODEL_CADANGAN = ["gemini-flash-lite-latest", "gemini-3.8-flash"]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(Exception):
    pass


def _pesan_error(status: int, isi: str) -> str:
    if status == 429:
        return "Kuota gratis Gemini sedang habis, coba lagi sebentar."
    if status in (401, 403) or "API key" in isi:
        return "API key Gemini salah atau belum aktif. Atur ulang lewat /gemini_key <API_KEY>."
    if status == 404:
        return "Nama model Gemini tidak dikenal (cek pengaturan gemini.model di config.json)."
    if status >= 500:
        return f"Server Gemini sedang sibuk/gangguan (kode {status}), coba lagi sebentar."
    return f"Gemini menolak permintaan (kode {status})."


def ambil_cfg(cfg: dict) -> tuple[str, str]:
    """Ambil (api_key, model) dari config.json."""
    g = cfg.get("gemini") or {}
    if isinstance(g, dict):
        key = str(g.get("api_key") or "").strip()
        model = str(g.get("model") or "").strip() or MODEL_BAWAAN
        return key, model
    return "", MODEL_BAWAAN


def _post_json(url: str, body: dict, api_key: str, timeout: float) -> tuple[int, str]:
    """Kirim POST JSON ke Gemini. Kalau SSL requests gagal di Windows, otomatis jatuh ke curl.exe."""
    try:
        r = requests.post(
            url,
            json=body,
            headers={"x-goog-api-key": api_key},
            timeout=timeout,
        )
        return r.status_code, r.text
    except requests.exceptions.SSLError:
        # Cadangan: curl bawaan Windows memakai sertifikat sistem Windows
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            proc = subprocess.run(
                [
                    "curl.exe", "-sS", "-w", "\n%{http_code}",
                    "-X", "POST", url,
                    "-H", "Content-Type: application/json",
                    "-H", f"x-goog-api-key: {api_key}",
                    "--max-time", str(int(timeout)),
                    "--data-binary", "@-",
                ],
                input=payload,
                capture_output=True,
                timeout=timeout + 5,
            )
        except subprocess.TimeoutExpired:
            raise GeminiError("Gemini terlalu lama menjawab, coba lagi.") from None
        except Exception as e:
            raise GeminiError(f"Tidak bisa menghubungi Gemini ({type(e).__name__}).") from None
        out = proc.stdout.decode("utf-8", errors="replace")
        if "\n" not in out:
            raise GeminiError("Tidak bisa menghubungi Gemini (SSL/jaringan bermasalah).")
        teks_resp, kode_s = out.rsplit("\n", 1)
        try:
            return int(kode_s.strip()), teks_resp
        except ValueError:
            raise GeminiError("Jawaban server Gemini tidak terbaca.") from None
    except requests.Timeout:
        raise GeminiError("Gemini terlalu lama menjawab, coba lagi.") from None
    except requests.RequestException as e:
        raise GeminiError(f"Tidak bisa menghubungi Gemini ({type(e).__name__}).") from None


def _kirim(api_key: str, body: dict, model: str = "", timeout: float = 35,
           coba_lain: bool = True) -> str:
    if not api_key:
        raise GeminiError("API key Gemini belum diisi. Kirim: /gemini_key <API_KEY>")
    daftar = [model or MODEL_BAWAAN]
    if coba_lain:
        daftar += [m for m in MODEL_CADANGAN if m not in daftar]
    status, teks_resp = 0, ""
    for i, m in enumerate(daftar):
        for _ in range(2 if (coba_lain and i == 0) else 1):
            status, teks_resp = _post_json(URL.format(model=m), body, api_key, timeout)
            if status == 200:
                break
            logging.warning("Gemini %s HTTP %s: %s", m, status, teks_resp[:250])
            if status < 500:
                break
            time.sleep(1.5)
        if status == 200 or (status not in (404, 429) and status < 500):
            break
    if status != 200:
        raise GeminiError(_pesan_error(status, teks_resp))
    try:
        data = json.loads(teks_resp)
        parts = data["candidates"][0]["content"]["parts"]
        teks = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    except (KeyError, IndexError, ValueError):
        teks = ""
    if not teks:
        raise GeminiError("Gemini tidak memberi jawaban (mungkin diblokir filter keamanan).")
    return teks


def tanya(api_key: str, prompt: str, system: str = "", model: str = "",
          timeout: float = 35, suhu: float = 0.3, coba_lain: bool = True,
          riwayat: list[tuple[str, str]] | None = None) -> str:
    """Kirim pertanyaan teks ke Gemini API (bisa menyertakan riwayat chat singkat)."""
    contents: list[dict[str, Any]] = []
    for u_teks, m_teks in (riwayat or []):
        contents.append({"role": "user", "parts": [{"text": u_teks}]})
        contents.append({"role": "model", "parts": [{"text": m_teks}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": suhu, "maxOutputTokens": 2048},
    }
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    return _kirim(api_key, body, model=model, timeout=timeout, coba_lain=coba_lain)


def tanya_gambar(api_key: str, image_bytes: bytes, prompt: str, system: str = "",
                 mime_type: str = "image/jpeg", model: str = "", timeout: float = 45,
                 suhu: float = 0.1, coba_lain: bool = True) -> str:
    """Kirim gambar + prompt ke Gemini Vision, kembalikan teks analisis."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    body: dict[str, Any] = {
        "contents": [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": b64}},
                {"text": prompt},
            ],
        }],
        "generationConfig": {"temperature": suhu, "maxOutputTokens": 2048},
    }
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    return _kirim(api_key, body, model=model, timeout=timeout, coba_lain=coba_lain)


def ke_html_telegram(teks: str) -> str:
    """Ubah markdown sederhana dari Gemini (**tebal**, heading) menjadi HTML aman untuk Telegram."""
    t = html.escape(teks.strip())
    # Heading markdown ### Judul -> <b>Judul</b>
    t = re.sub(r"(?m)^#{1,4}\s+(.+)$", r"<b>\1</b>", t)
    # **bold** -> <b>bold</b>
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    # `code` -> <code>code</code>
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    # Bullet "* item" -> "• item"
    t = re.sub(r"(?m)^\s*[\*\-]\s+", "• ", t)
    return t


# ------------------------------------------------------------ konteks karakter & prompt RTNW

SISTEM_TANYA = (
    "Kamu asisten racik build Ragnarok: The New World (RTNW) untuk jasa optimasi DPS milik Philip. "
    "Jawab dalam Bahasa Indonesia yang ringkas, langsung ke inti, enak dibaca di HP (maks ~12 baris, pakai poin). "
    "WAJIB berpatokan pada data karakter yang diberikan di konteks (stat, DPS, target, prioritas model). "
    "JANGAN mengarang angka stat atau efek kartu/equip yang tidak kamu ketahui pasti; kalau belum pasti, sebutkan singkat. "
    "Fokus hanya pada hal yang menaikkan angka Damage Challenge (bukan HP/DEF/tahan pukul)."
)

SISTEM_VISION = (
    "Kamu asisten pembaca layar game Ragnarok: The New World (RTNW) untuk optimasi DPS. "
    "Baca isi layar yang terlihat secara akurat dan ringkas dalam Bahasa Indonesia (enak dibaca di HP). "
    "JANGAN menebak teks yang buram/tidak terbaca — tulis '(kurang jelas)' jika buram."
)

PROMPT_VISION_UMUM = (
    "Identifikasi halaman game Ragnarok pada gambar ini (misalnya Equipment/Kartu, Detailed Stats, "
    "Enchant/Gem, Skills, atau panel Statistics pasca-test). Lalu:\n"
    "1. Daftar singkat item/kartu/stat/skill penting yang terlihat (beserta +refine / level / angka jika terlihat).\n"
    "2. Sorot 2-3 temuan paling penting untuk menaikkan DPS Damage Challenge (misal slot kartu kosong/kurang cocok, "
    "stat mubazir untuk dummy Humanoid Medium Neutral, atau upgrade paling terasa)."
)


def konteks_karakter(pid: str, profil: dict, s_test: dict) -> str:
    """Bangun ringkasan data asli karakter aktif untuk disuntikkan ke prompt Gemini."""
    nama = profil.get("nick") or profil.get("nama") or pid
    job = profil.get("job") or "(belum diisi)"
    target = int(profil.get("target") or 0)
    ok = catatan.baca_ok(pid)
    baris = [
        f"Karakter: {nama} | Job: {job}",
        f"Sasaran test: {s_test.get('nama', 'Dummy')} "
        f"({s_test.get('ras', 'Human')}, {s_test.get('ukuran', 'Medium')}, {s_test.get('elemen', 'Neutral')})",
    ]
    if ok:
        awal = ok[0]["dps"]
        rekor = max(r["dps"] for r in ok)
        akhir = ok[-1]["dps"]
        baris.append(
            f"DPS: awal {umum.fmt(awal)}, terakhir {umum.fmt(akhir)}, rekor {umum.fmt(rekor)} "
            f"({len(ok)} test)" + (f" | Target: {umum.fmt(target)}" if target else "")
        )
    elif target:
        baris.append(f"Target DPS: {umum.fmt(target)} (belum ada hasil test)")

    # Detailed Stats terakhir
    log_st = bacabuild.baca_log(pid)
    if log_st:
        gabung: dict[str, Any] = {}
        for _, s in log_st:
            gabung.update(s)
        stat_log = statistik.baca_log(pid)
        sumber_skill = stat_log[-1].get("sumber") if stat_log else None
        # Pilih stat ofensif utama agar ringkas
        kunci_penting = [
            "ATK", "ATK%", "M.ATK", "M.ATK%", "PDMG Bonus%", "MDMG Bonus%",
            "Ranged PDMG%", "Melee PDMG%", "Skill DMG%", "Normal Attack DMG%",
            "Elemental DMG%", "Final DMG", "Final PDMG", "Final MDMG",
            "CRIT", "CRIT DMG%", "Ignore P.DEF", "Ignore P.DEF%", "Ignore M.DEF", "Ignore M.DEF%",
            "Attack Frequency", "Variable Cast Time%",
            "DMG vs Human%", "DMG vs Demi-Human%", "DMG vs Medium%", "DMG vs Neutral%",
        ]
        st_ringkas = [f"{k}={gabung[k]}" for k in kunci_penting if k in gabung]
        if st_ringkas:
            baris.append("Detailed Stats: " + ", ".join(st_ringkas))
        try:
            prio, warn, pb = rumus.prioritas_stat(gabung, s_test, job, sumber_skill)
            if prio:
                top = ", ".join(f"{x['singkat']} ({x['naik_pct']:+.1f}%)" for x in prio[:5])
                baris.append("Prioritas stat (model rumus.py): " + top)
            if warn:
                baris.append("Catatan cap: " + " | ".join(warn))
        except Exception:
            pass
        if sumber_skill:
            top_sk = ", ".join(f"{r.get('nama')} {r.get('persen')}%" for r in sumber_skill[:5])
            baris.append("Kontribusi skill terakhir: " + top_sk)
    else:
        baris.append("Detailed Stats: belum tersimpan.")

    return "\n".join(baris)
