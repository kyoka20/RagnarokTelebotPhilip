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
import importlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

import umum

FILE_SHA = umum.FOLDER / "log" / "auto_update_sha.txt"
FILE_REQ_SHA = umum.FOLDER / "log" / "requirements_sha.txt"
DILARANG_EKSTRA = {"4_jalankan_bot.bat", "4b_jalankan_bot_minimize.bat", "jaga_bot.ps1", "jaga_bot_diam.vbs"}
# `database/` & `database_ikon/` diunduh sendiri oleh bot di laptop (datagame.perbarui, tiap hari).
# Versi di GitHub bisa lebih tua -> jangan sampai menimpa database yang lebih baru di laptop.
FOLDER_DIURUS_LAPTOP = {"database", "database_ikon"}
EKSTENSI_BOLEH = (".py", ".json", ".txt", ".md")
DEFAULT_SYNC_REPO = "kyoka20/ro-bot-logs"

_ETAG_CACHE: dict[str, str] = {}
_SYNC_SIG_TERAKHIR: tuple[int, int, str] | None = None
_REPO_PRIVATE_OK: set[str] = set()
_BRANCH_OK: set[tuple[str, str]] = set()


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


def cek_commit_terbaru(repo: str, branch: str = "main", token: str = "", paksa: bool = False) -> tuple[str | None, str]:
    """Kembalikan (sha, pesan_commit_baris_pertama) dari GitHub API.

    Memakai HTTP ETag (`If-None-Match`): bila tidak ada commit baru, GitHub balas 304 (0 byte,
    tidak menghabiskan kuota rate-limit) dan fungsi mengembalikan `(None, "")`.
    """
    kunci = f"{repo.strip().strip('/')}:{branch.strip() or 'main'}"
    url = f"https://api.github.com/repos/{repo.strip().strip('/')}/commits/{branch.strip() or 'main'}"
    hdr = _headers(token)
    if not paksa and kunci in _ETAG_CACHE:
        hdr["If-None-Match"] = _ETAG_CACHE[kunci]
    r = requests.get(url, headers=hdr, timeout=20)
    if r.status_code == 304:
        return None, ""
    r.raise_for_status()
    etag = r.headers.get("ETag")
    if etag:
        _ETAG_CACHE[kunci] = etag
    d = r.json()
    sha = str(d.get("sha") or "").strip()
    pesan = str((d.get("commit") or {}).get("message") or "").splitlines()[0].strip()
    if not sha:
        raise ValueError("SHA commit tidak ditemukan di respons GitHub.")
    return sha, pesan


def lupakan_etag() -> None:
    """Dipanggil kalau cek/unduh gagal di tengah jalan: cek berikutnya harus menarik ulang,
    bukan dapat 304 lalu mengira sudah terbaru (update bisa terlewat sampai ada commit lain)."""
    _ETAG_CACHE.clear()


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
        if (bagian[0].lower() in dilarang_folder or bagian[0].lower() in FOLDER_DIURUS_LAPTOP
                or bagian[0].startswith(".")):
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
    mentah = au.get("interval_menit")
    # Default baru 2 menit (aman & ringan karena pakai ETag 304). Nilai lama 15 otomatis turun ke 2 kecuali diset manual.
    if mentah is None or (int(mentah) == 15 and not au.get("interval_kustom")):
        interval = 2
    else:
        interval = max(2, int(mentah))
    return {
        "repo": str(au.get("repo") or "").strip(),
        "branch": str(au.get("branch") or "main").strip() or "main",
        "token": str(au.get("token") or "").strip(),
        "interval_menit": interval,
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
        "repo": str(sl.get("repo") or DEFAULT_SYNC_REPO).strip(),
        "branch": str(sl.get("branch") or "logs").strip() or "logs",
        "token": str(sl.get("token") or au.get("token") or "").strip(),
        "interval_menit": max(2, int(sl.get("interval_menit") or 5)),
        "aktif": bool(sl.get("aktif", False)),
    }


def _cek_repo_private(repo: str, token: str) -> str:
    """Pastikan repo bersifat PRIVATE agar log/data klien tidak bocor ke publik. Kembalikan default_branch."""
    if not token:
        raise ValueError("Token GitHub belum diisi (wajib untuk push log ke repo private).")
    repo_clean = repo.strip().strip("/")
    url = f"https://api.github.com/repos/{repo_clean}"
    r = requests.get(url, headers=_headers(token), timeout=20)
    r.raise_for_status()
    d = r.json()
    if not d.get("private"):
        raise ValueError(f"Repo {repo} masih PUBLIK! Jadikan Private dulu (atau pakai repo private khusus log) agar data klien aman.")
    _REPO_PRIVATE_OK.add(repo_clean)
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


def kirim_log(repo: str, branch: str, token: str, ringkas_profil: dict[str, Any],
              maks_kb: int = 200, paksa: bool = False) -> list[str]:
    """Kirim ekor bot.log (maks_kb KB) + ringkasan profil ke branch khusus (default `logs`) di repo PRIVATE.

    Ringan untuk laptop: cek mtime+size bot.log & hash profil dulu; kalau tidak berubah, 0 request HTTP.
    """
    global _SYNC_SIG_TERAKHIR
    if branch.strip().lower() in ("main", "master"):
        raise ValueError("Branch sync_log tidak boleh main/master (pakai branch khusus seperti 'logs').")

    file_log = umum.FOLDER / "log" / "bot.log"
    st = file_log.stat() if file_log.exists() else None
    profil_tanpa_jam = {k: v for k, v in ringkas_profil.items() if k != "diperbarui"}
    sig_profil = hashlib.sha1(json.dumps(profil_tanpa_jam, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    sig_baru = (st.st_mtime_ns if st else 0, st.st_size if st else 0, sig_profil)
    if not paksa and _SYNC_SIG_TERAKHIR == sig_baru:
        return []  # tidak ada perubahan sejak sync terakhir -> 0 HTTP request

    repo_clean = repo.strip().strip("/")
    if repo_clean not in _REPO_PRIVATE_OK or (repo_clean, branch) not in _BRANCH_OK:
        default_branch = _cek_repo_private(repo_clean, token)
        _pastikan_branch(repo_clean, branch, default_branch, token)
        _BRANCH_OK.add((repo_clean, branch))

    terkirim: list[str] = []
    cap = datetime.now().strftime("%Y-%m-%d %H:%M")

    if file_log.exists():
        mentah = file_log.read_bytes()
        batas = maks_kb * 1024
        if len(mentah) > batas:
            potong = mentah[-batas:]
            nl = potong.find(b"\n")
            mentah = potong[nl + 1:] if nl != -1 else potong
        teks_log = sensor_rahasia(mentah.decode("utf-8", "replace"))
        if _upload_konten(repo_clean, branch, token, "telemetry/bot.log", teks_log.encode("utf-8"),
                          f"sync log {cap}"):
            terkirim.append("telemetry/bot.log")

    data_profil = sensor_rahasia(json.dumps(ringkas_profil, ensure_ascii=False, indent=2)).encode("utf-8")
    if _upload_konten(repo_clean, branch, token, "telemetry/ringkas_profil.json", data_profil,
                      f"sync profil {cap}"):
        terkirim.append("telemetry/ringkas_profil.json")

    _SYNC_SIG_TERAKHIR = sig_baru
    return terkirim


# ---------------------------------------------------------------- Auto-install paket (requirements.txt)

_MODUL_BOOST = (
    ("OpenCV", "cv2"),
    ("RapidOCR", "rapidocr_onnxruntime"),
    ("WindowsCapture", "windows_capture"),
    ("RapidFuzz", "rapidfuzz"),
    ("orjson", "orjson"),
    ("HTTP/2", "httpx"),
    ("psutil", "psutil"),
    ("FFmpeg", "imageio_ffmpeg"),
)

_psutil_mod = None
_psutil_dicek = False
_cpu_terakhir_t = 0.0
_cpu_terakhir_v = 0.0


def _psutil():
    global _psutil_mod, _psutil_dicek
    if not _psutil_dicek:
        _psutil_dicek = True
        try:
            import psutil  # type: ignore
            psutil.cpu_percent(interval=None)  # priming non-blocking
            _psutil_mod = psutil
        except Exception:
            _psutil_mod = None
    return _psutil_mod


def reset_cache_boost() -> None:
    global _psutil_dicek
    _psutil_dicek = False


def beban_cpu_tinggi(batas: float = 85.0) -> bool:
    """True bila CPU laptop sedang tinggi (> batas%). Non-blocking, dicek maks tiap 5 detik."""
    global _cpu_terakhir_t, _cpu_terakhir_v
    ps = _psutil()
    if ps is None:
        return False
    import time
    sekarang = time.monotonic()
    if sekarang - _cpu_terakhir_t >= 5.0:
        try:
            _cpu_terakhir_v = float(ps.cpu_percent(interval=None))
            _cpu_terakhir_t = sekarang
        except Exception:
            return False
    return _cpu_terakhir_v >= batas


def info_sistem() -> str:
    """Ringkasan singkat RAM bot & CPU/RAM laptop (memakai psutil bila terpasang)."""
    ps = _psutil()
    if ps is None:
        return ""
    try:
        import os
        ram_bot = ps.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        vm = ps.virtual_memory()
        cpu = ps.cpu_percent(interval=None)
        return f"RAM bot {ram_bot:.0f} MB | Laptop CPU {cpu:.0f}%, RAM {vm.percent:.0f}%"
    except Exception:
        return ""


def diagnosa_laptop() -> str:
    """Cek siapa pelaku pemakan CPU & RAM terbesar di laptop (bot kita vs aplikasi lain)."""
    import os
    import time
    ps = _psutil()
    if ps is None:
        return ("⚠️ Modul <code>psutil</code> belum selesai terpasang.\n"
                "Tunggu ±1–2 menit (atau cek <code>/auto_update</code>) lalu jalankan <code>/cek_laptop</code> lagi.")
    pid_bot = os.getpid()
    n_cpu = ps.cpu_count(logical=True) or 1
    procs = []
    for p in ps.process_iter(["pid", "name"]):
        try:
            p.cpu_percent(interval=None)
            procs.append(p)
        except Exception:
            pass
    ps.cpu_percent(interval=None)
    time.sleep(1.0)
    cpu_total = ps.cpu_percent(interval=None)
    vm = ps.virtual_memory()
    bot_cpu, bot_ram = 0.0, 0.0
    daftar = []
    ada_pip = False
    for p in procs:
        try:
            nama = (p.info.get("name") or "?").strip()
            if nama.lower() in ("system idle process", "idle"):
                continue
            c = p.cpu_percent(interval=None) / n_cpu
            m = p.memory_info().rss / (1024 * 1024)
            if p.pid == pid_bot:
                bot_cpu, bot_ram = c, m
            if any(k in nama.lower() for k in ("pip", "uv.exe")):
                ada_pip = True
            daftar.append((c, m, p.pid, nama))
        except Exception:
            pass
    # Gabungkan proses dengan nama sama (mis. Chrome banyak tab)
    gabung: dict[str, list[float]] = {}
    for c, m, pid, nama in daftar:
        k = f"{nama} (BOT KITA)" if pid == pid_bot else nama
        g = gabung.setdefault(k, [0.0, 0.0, 0])
        g[0] += c
        g[1] += m
        g[2] += 1
    top_cpu = sorted(gabung.items(), key=lambda x: -x[1][0])[:6]
    top_ram = sorted(gabung.items(), key=lambda x: -x[1][1])[:6]
    vonis = ("✅ <b>Bot kita BUKAN pelakunya</b> (ringan)."
             if bot_cpu < 10 and bot_ram < 450
             else "⚠️ <b>Bot kita sedang lumayan berat</b> — cek detail di bawah.")
    baris = [
        "🩺 <b>DIAGNOSA LAPTOP</b>",
        f"• CPU total: <b>{cpu_total:.0f}%</b> | RAM: <b>{vm.used / (1024**3):.1f} / {vm.total / (1024**3):.1f} GB ({vm.percent:.0f}%)</b>",
        f"• Bot kita: CPU <b>{bot_cpu:.1f}%</b> | RAM <b>{bot_ram:.0f} MB</b>",
        f"• Vonis: {vonis}",
    ]
    if ada_pip:
        baris.append("• ⏳ <i>Catatan: pip/uv sedang install paket update di belakang layar (sementara bikin berat 1–2 menit).</i>")
    baris.append("\n🔥 <b>Top Pemakan CPU:</b>")
    import html as _html
    for k, (c, m, cnt) in top_cpu:
        t_cnt = f" ×{int(cnt)}" if cnt > 1 else ""
        baris.append(f"• {_html.escape(k)}{t_cnt}: <b>{c:.1f}% CPU</b> ({m:.0f} MB)")
    baris.append("\n🧠 <b>Top Pemakan RAM:</b>")
    for k, (c, m, cnt) in top_ram:
        t_cnt = f" ×{int(cnt)}" if cnt > 1 else ""
        baris.append(f"• {_html.escape(k)}{t_cnt}: <b>{m:.0f} MB</b> ({c:.1f}% CPU)")
    return "\n".join(baris)


def status_modul_boost() -> dict[str, bool]:
    """Cek modul akselerasi Tier S/A mana saja yang sudah terpasang di environment aktif."""
    importlib.invalidate_caches()
    hasil: dict[str, bool] = {}
    for label, nama_mod in _MODUL_BOOST:
        hasil[label] = importlib.util.find_spec(nama_mod) is not None
    return hasil


def pasang_requirements(log=None, paksa: bool = False) -> tuple[bool, str]:
    """Pasang paket di requirements.txt otomatis bila berubah (atau belum pernah dipasang).

    Aman & non-destruktif: pakai pip bawaan venv, fallback ke `uv pip install` (sama dengan 1_install.bat).
    Mengembalikan (ada_install_baru, ringkasan_teks).
    """
    req = umum.FOLDER / "requirements.txt"
    if not req.exists():
        return False, "requirements.txt tidak ditemukan"
    isi = req.read_bytes()
    sha_baru = hashlib.sha1(isi).hexdigest()
    sha_lama = ""
    try:
        sha_lama = FILE_REQ_SHA.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    if not paksa and sha_lama == sha_baru:
        return False, "sudah sesuai"

    cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd = None
    try:
        cek_pip = subprocess.run([sys.executable, "-m", "pip", "--version"],
                                 capture_output=True, timeout=20, creationflags=cflags)
        if cek_pip.returncode == 0:
            cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                   "--no-input", "-r", str(req)]
    except Exception:
        pass
    if cmd is None:
        uv_exe = shutil.which("uv")
        if uv_exe:
            cmd = [uv_exe, "pip", "install", "--python", sys.executable, "-r", str(req)]
    if cmd is None:
        return False, "pip dan uv tidak ditemukan"

    if log:
        log.info("Memasang paket baru dari requirements.txt (%s)...", sha_baru[:8])
    try:
        r = subprocess.run(cmd, cwd=str(umum.FOLDER), capture_output=True, timeout=360,
                           creationflags=cflags)
    except Exception as e:
        return False, f"gagal menjalankan installer: {e}"
    if r.returncode != 0:
        err = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()
        return False, f"install gagal (kode {r.returncode}): {err[-400:]}"

    importlib.invalidate_caches()
    FILE_REQ_SHA.parent.mkdir(parents=True, exist_ok=True)
    FILE_REQ_SHA.write_text(sha_baru, encoding="utf-8")
    st = status_modul_boost()
    aktif = [k for k, v in st.items() if v]
    ringkas = f"paket terpasang ({', '.join(aktif) if aktif else 'dasar'})"
    if log:
        log.info("Auto-install requirements.txt selesai: %s", ringkas)
    return True, ringkas
