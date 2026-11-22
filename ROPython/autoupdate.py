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

import io
import json
import zipfile
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
