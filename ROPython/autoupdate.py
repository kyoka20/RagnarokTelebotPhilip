"""Auto-update bot otomatis dari repositori GitHub (publik atau private).

Alur aman:
1. Cek SHA commit terbaru di GitHub API (`interval_menit`, default 15 menit).
2. Jika SHA berbeda dari `log/auto_update_sha.txt`, unduh zipball branch.
3. Ekstrak hanya file kode/database_tetap di dalam `ROPython/` (atau akar repo) yang
   benar-benar berubah dan tidak masuk daftar terlarang (config.json, data, log, .venv, dll.).
4. Kembalikan `{path_relatif: bytes}` untuk dipasang lewat pipeline aman `bot.py`
   (cek sintaks, cadangan, uji `import bot`, rollback otomatis kalau error, restart).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

import umum

FILE_SHA = umum.FOLDER / "log" / "auto_update_sha.txt"
DILARANG_EKSTRA = {"4_jalankan_bot.bat", "4b_jalankan_bot_minimize.bat", "jaga_bot.ps1", "jaga_bot_diam.vbs"}
EKSTENSI_BOLEH = (".py", ".json", ".txt", ".md")


def _headers(token: str = "") -> dict[str, str]:
    h = {"User-Agent": "ROPython-AutoUpdate/1.0", "Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token.strip()}"
    return h


def sha_lokal() -> str:
    try:
        return FILE_SHA.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def simpan_sha(sha: str) -> None:
    FILE_SHA.parent.mkdir(parents=True, exist_ok=True)
    FILE_SHA.write_text(sha.strip(), encoding="utf-8")


def cek_commit_terbaru(repo: str, branch: str = "main", token: str = "") -> tuple[str, str]:
    """Kembalikan (sha, pesan_commit_baris_pertama) dari GitHub API."""
    url = f"https://api.github.com/repos/{repo.strip().strip('/')}/commits/{branch.strip() or 'main'}"
    r = requests.get(url, headers=_headers(token), timeout=30)
    r.raise_for_status()
    d = r.json()
    sha = str(d.get("sha") or "").strip()
    pesan = str((d.get("commit") or {}).get("message") or "").splitlines()[0].strip()
    if not sha:
        raise ValueError("SHA commit tidak ditemukan di respons GitHub.")
    return sha, pesan


def unduh_berkas_berubah(repo: str, branch: str, token: str, dilarang_folder: set[str]) -> tuple[dict[str, bytes], list[str]]:
    """Unduh zipball branch GitHub -> ({path_relatif: bytes} yang berubah saja, daftar dilewati)."""
    url = f"https://api.github.com/repos/{repo.strip().strip('/')}/zipball/{branch.strip() or 'main'}"
    r = requests.get(url, headers=_headers(token), timeout=180)
    r.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    mentah: dict[str, bytes] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        p = info.filename.replace("\\", "/")
        # Zipball GitHub selalu punya 1 folder induk: "<owner>-<repo>-<sha>/..."
        if "/" in p:
            p = p.split("/", 1)[1]
        mentah[p] = zf.read(info)

    # Jika repo berisi folder ROPython/, ambil isinya saja.
    ada_ropython = any(p.startswith("ROPython/") for p in mentah)
    berubah: dict[str, bytes] = {}
    dilewati: list[str] = []

    for p, data in mentah.items():
        if ada_ropython:
            if not p.startswith("ROPython/"):
                continue
            p = p[len("ROPython/"):]
        bagian = [b for b in p.split("/") if b]
        if not bagian or any(b in ("..", ".") for b in bagian):
            continue
        if bagian[0].lower() in dilarang_folder or bagian[0].startswith("."):
            continue
        if p.lower() in DILARANG_EKSTRA or not p.lower().endswith(EKSTENSI_BOLEH):
            continue
        # Hanya file yang ukurannya masuk akal (maks 5 MB per file)
        if len(data) > 5_000_000:
            dilewati.append(p)
            continue

        rel = "/".join(bagian)
        # Validasi sintaks .py & .json
        if rel.lower().endswith(".py"):
            try:
                compile(data.decode("utf-8-sig"), rel, "exec")
            except (UnicodeDecodeError, SyntaxError) as e:
                raise ValueError(f"{rel} bermasalah: {e}") from None
        elif rel.lower().endswith(".json"):
            try:
                json.loads(data.decode("utf-8-sig"))
            except ValueError as e:
                raise ValueError(f"{rel} bukan JSON valid: {e}") from None

        # Bandingkan dengan file lokal -> hanya pasang jika benar-benar berubah
        tujuan = umum.FOLDER / rel
        if tujuan.exists():
            try:
                if tujuan.read_bytes() == data:
                    continue
            except OSError:
                pass
        berubah[rel] = data

    return berubah, dilewati


def info_config(cfg: dict[str, Any]) -> dict[str, Any]:
    au = cfg.get("auto_update") or {}
    return {
        "repo": str(au.get("repo") or "").strip(),
        "branch": str(au.get("branch") or "main").strip() or "main",
        "token": str(au.get("token") or "").strip(),
        "interval_menit": max(2, int(au.get("interval_menit") or 15)),
        "aktif": bool(au.get("aktif", True)),
    }


# ---------------------------------------------------------------- Sync Log ke GitHub (branch khusus `logs`, wajib repo PRIVATE)

_POLA_RAHASIA = [
    (re.compile(r"\b\d{8,11}:[A-Za-z0-9_-]{30,}\b"), "[TOKEN_TG_DISENSOR]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{16,}\b"), "[TOKEN_GH_DISENSOR]"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"), "[APIKEY_DISENSOR]"),
]


def sensor_rahasia(teks: str) -> str:
    """Pastikan tidak ada token/API key yang ikut terkirim ke log GitHub."""
    for pola, ganti in _POLA_RAHASIA:
        teks = pola.sub(ganti, teks)
    return teks


def info_sync_log(cfg: dict[str, Any]) -> dict[str, Any]:
    sl = cfg.get("sync_log") or {}
    au = cfg.get("auto_update") or {}
    return {
        "repo": str(sl.get("repo") or au.get("repo") or "").strip(),
        "branch": str(sl.get("branch") or "logs").strip() or "logs",
        "token": str(sl.get("token") or au.get("token") or "").strip(),
        "interval_menit": max(5, int(sl.get("interval_menit") or 30)),
        "aktif": bool(sl.get("aktif", False)),
    }


def _cek_repo_private(repo: str, token: str) -> str:
    """Pastikan repo bersifat PRIVATE agar log/data klien tidak bocor ke publik. Kembalikan default_branch."""
    if not token:
        raise ValueError("Token GitHub belum diisi (wajib untuk push log ke repo private).")
    url = f"https://api.github.com/repos/{repo.strip().strip('/')}"
    r = requests.get(url, headers=_headers(token), timeout=20)
    r.raise_for_status()
    d = r.json()
    if not d.get("private"):
        raise ValueError(f"Repo {repo} masih PUBLIK! Jadikan Private dulu (atau pakai repo private khusus log) agar data klien aman.")
    return str(d.get("default_branch") or "main")


def _pastikan_branch(repo: str, branch: str, default_branch: str, token: str) -> None:
    """Buat branch `branch` (mis. `logs`) dari default_branch bila belum ada di GitHub."""
    repo_clean = repo.strip().strip("/")
    url_ref = f"https://api.github.com/repos/{repo_clean}/git/ref/heads/{branch}"
    r = requests.get(url_ref, headers=_headers(token), timeout=20)
    if r.status_code == 200:
        return
    if r.status_code != 404:
        r.raise_for_status()
    r_base = requests.get(f"https://api.github.com/repos/{repo_clean}/git/ref/heads/{default_branch}",
                          headers=_headers(token), timeout=20)
    r_base.raise_for_status()
    sha_base = r_base.json()["object"]["sha"]
    r_new = requests.post(f"https://api.github.com/repos/{repo_clean}/git/refs",
                          headers=_headers(token),
                          json={"ref": f"refs/heads/{branch}", "sha": sha_base},
                          timeout=20)
    if r_new.status_code not in (200, 201, 422):
        r_new.raise_for_status()


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _upload_konten(repo: str, branch: str, token: str, path_repo: str, data: bytes, pesan: str) -> bool:
    """Upload/update 1 file lewat GitHub Contents API. Return False bila isi sama persis (skip)."""
    repo_clean = repo.strip().strip("/")
    url = f"https://api.github.com/repos/{repo_clean}/contents/{path_repo.lstrip('/')}"
    r = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=20)
    sha_lama = None
    if r.status_code == 200:
        sha_lama = r.json().get("sha")
        if sha_lama == _git_blob_sha(data):
            return False
    elif r.status_code != 404:
        r.raise_for_status()
    payload: dict[str, Any] = {
        "message": pesan,
        "content": base64.b64encode(data).decode("ascii"),
        "branch": branch,
    }
    if sha_lama:
        payload["sha"] = sha_lama
    r_put = requests.put(url, headers=_headers(token), json=payload, timeout=30)
    r_put.raise_for_status()
    return True


def kirim_log(repo: str, branch: str, token: str, ringkas_profil: dict[str, Any], maks_kb: int = 200) -> list[str]:
    """Kirim ekor bot.log (maks_kb KB) + ringkasan profil ke branch khusus (default `logs`) di repo PRIVATE."""
    if branch.strip().lower() in ("main", "master"):
        raise ValueError("Branch sync_log tidak boleh main/master (pakai branch khusus seperti 'logs').")
    default_branch = _cek_repo_private(repo, token)
    _pastikan_branch(repo, branch, default_branch, token)

    terkirim: list[str] = []
    cap = datetime.now().strftime("%Y-%m-%d %H:%M")

    file_log = umum.FOLDER / "log" / "bot.log"
    if file_log.exists():
        mentah = file_log.read_bytes()
        batas = maks_kb * 1024
        if len(mentah) > batas:
            potong = mentah[-batas:]
            nl = potong.find(b"\n")
            mentah = potong[nl + 1:] if nl != -1 else potong
        teks_log = sensor_rahasia(mentah.decode("utf-8", "replace"))
        if _upload_konten(repo, branch, token, "telemetry/bot.log", teks_log.encode("utf-8"),
                          f"sync log {cap}"):
            terkirim.append("telemetry/bot.log")

    data_profil = sensor_rahasia(json.dumps(ringkas_profil, ensure_ascii=False, indent=2)).encode("utf-8")
    if _upload_konten(repo, branch, token, "telemetry/ringkas_profil.json", data_profil,
                      f"sync profil {cap}"):
        terkirim.append("telemetry/ringkas_profil.json")

    return terkirim
