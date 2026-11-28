"""Komunikasi dengan Telegram Bot API + antrean kirim yang tahan internet putus."""
from __future__ import annotations

import json
import queue
import threading
import time

import requests

_httpx_mod = None
_httpx_dicek = False


def _httpx():
    global _httpx_mod, _httpx_dicek
    if not _httpx_dicek:
        _httpx_dicek = True
        try:
            import httpx  # type: ignore
            _httpx_mod = httpx
        except Exception:
            _httpx_mod = None
    return _httpx_mod


def reset_cache_boost() -> None:
    global _httpx_dicek
    _httpx_dicek = False


class TelegramError(Exception):
    """Ditolak Telegram (mis. token salah). Tidak ada gunanya dicoba ulang."""


class TelegramSementara(Exception):
    """Gangguan sementara (internet putus, server sibuk). Boleh dicoba ulang."""

    def __init__(self, pesan: str, tunggu: float = 0):
        super().__init__(pesan)
        self.tunggu = tunggu


BATAS_TEKS = 3900  # batas Telegram 4096; sisakan ruang


def potong_pesan(teks: str, batas: int = BATAS_TEKS) -> list[str]:
    """Pecah pesan panjang di batas baris (bukan di tengah tag HTML), tiap bagian <= batas."""
    if len(teks) <= batas:
        return [teks]
    bagian, kini = [], ""
    for baris in teks.split("\n"):
        while len(baris) > batas:  # satu baris super panjang (jarang): potong paksa
            if kini:
                bagian.append(kini)
                kini = ""
            bagian.append(baris[:batas])
            baris = baris[batas:]
        if kini and len(kini) + 1 + len(baris) > batas:
            bagian.append(kini)
            kini = baris
        else:
            kini = f"{kini}\n{baris}" if kini else baris
    if kini.strip():
        bagian.append(kini)
    return bagian


class Telegram:
    def __init__(self, token: str):
        self.token = token
        # Tiap thread (ambil perintah / kirim notif) punya sambungan sendiri,
        # supaya yang satu tidak mengganggu yang lain.
        self._lokal = threading.local()

    def _sesi(self, baru: bool = False):
        s = getattr(self._lokal, "sesi", None)
        # Sambungan yang lama diam (> 45 detik) sering sudah diputus diam-diam oleh router,
        # dan memakainya bisa macet ~20 detik. Lebih cepat buat sambungan baru.
        sekarang = time.time()
        if sekarang - getattr(self._lokal, "terakhir", sekarang) > 45:
            baru = True
        self._lokal.terakhir = sekarang
        hx = _httpx()
        pakai_hx = hx is not None
        if s is not None and (baru or getattr(self._lokal, "pakai_hx", False) != pakai_hx):
            try:
                s.close()
            except Exception:
                pass
            s = None
        if s is None:
            if pakai_hx:
                try:
                    s = hx.Client(http2=True, timeout=30.0)
                except Exception:
                    s = hx.Client(http2=False, timeout=30.0)
            else:
                s = requests.Session()
            self._lokal.sesi = s
            self._lokal.pakai_hx = pakai_hx
        return s

    def _bersih(self, teks: str) -> str:
        return teks.replace(self.token, "***TOKEN***")

    def panggil(self, metode: str, data: dict | None = None, files: dict | None = None, timeout: float = 30):
        url = f"https://api.telegram.org/bot{self.token}/{metode}"
        hx = _httpx()
        err_conn = (requests.ConnectionError,) + ((hx.ConnectError, hx.RemoteProtocolError) if hx else ())
        err_req = (requests.RequestException,) + ((hx.HTTPError,) if hx else ())
        try:
            try:
                r = self._sesi().post(url, data=data, files=files, timeout=timeout)
            except err_conn:
                # Sambungan lama sering sudah diputus server diam-diam. Langsung coba
                # sekali lagi dengan sambungan baru, tanpa menunggu.
                r = self._sesi(baru=True).post(url, data=data, files=files, timeout=timeout)
        except err_req as e:
            self._sesi(baru=True)
            raise TelegramSementara(self._bersih(f"{type(e).__name__}: {e}")) from None
        try:
            isi = r.json()
        except ValueError:
            raise TelegramSementara(f"Jawaban Telegram tidak terbaca (HTTP {r.status_code})") from None
        if isi.get("ok"):
            return isi["result"]
        pesan = f"{isi.get('error_code')}: {isi.get('description')}"
        if r.status_code == 429:
            tunggu = (isi.get("parameters") or {}).get("retry_after", 5)
            raise TelegramSementara(pesan, tunggu)
        if r.status_code >= 500:
            raise TelegramSementara(pesan)
        raise TelegramError(pesan)

    def info_bot(self):
        return self.panggil("getMe", timeout=15)

    def ambil_update(self, offset: int | None, tunggu: int = 25):
        data = {"timeout": tunggu, "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            data["offset"] = offset
        return self.panggil("getUpdates", data, timeout=tunggu + 10)

    def kirim_teks(self, chat_id: int, teks: str, tombol: list[list[str]] | None = None,
                   hapus_tombol: bool = False):
        """tombol = baris-baris tombol jawaban (muncul di bawah kolom ketik).
        Pesan kepanjangan dipecah per baris (dulu dipotong di tengah tag HTML -> ditolak Telegram)."""
        bagian = potong_pesan(teks)
        for b in bagian[:-1]:
            self.kirim_teks(chat_id, b)
        teks = bagian[-1]
        data = {"chat_id": chat_id, "text": teks[:4096], "parse_mode": "HTML",
                "disable_web_page_preview": "true"}
        if tombol:
            data["reply_markup"] = json.dumps({
                "keyboard": [[{"text": t} for t in baris] for baris in tombol],
                "resize_keyboard": True, "one_time_keyboard": True})
        elif hapus_tombol:
            data["reply_markup"] = json.dumps({"remove_keyboard": True})
        return self.panggil("sendMessage", data)

    def hapus_pesan(self, chat_id: int, message_id: int) -> bool:
        try:
            self.panggil("deleteMessage", {"chat_id": chat_id, "message_id": message_id}, timeout=10)
            return True
        except Exception:
            return False

    def edit_teks(self, chat_id: int, message_id: int, teks: str) -> bool:
        try:
            self.panggil("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": teks[:4096],
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }, timeout=15)
            return True
        except Exception:
            return False

    def kirim_aksi(self, chat_id: int, aksi: str = "typing") -> None:
        try:
            self.panggil("sendChatAction", {"chat_id": chat_id, "action": aksi}, timeout=10)
        except Exception:
            pass

    def kirim_dokumen(self, chat_id: int, isi: bytes, nama: str, caption: str = ""):
        return self.panggil("sendDocument", {"chat_id": chat_id, "caption": caption[:1000], "parse_mode": "HTML"},
                            files={"document": (nama, isi)}, timeout=90)

    def kirim_foto(self, chat_id: int, foto: bytes, caption: str = "", nama: str = "foto.png"):
        return self.panggil(
            "sendPhoto",
            {"chat_id": chat_id, "caption": caption[:1000], "parse_mode": "HTML"},
            files={"photo": (nama, foto)}, timeout=90,
        )

    def kirim_animasi(self, chat_id: int, isi: bytes, caption: str = "", nama: str = "animasi.gif"):
        is_mp4 = (len(isi) > 12 and isi[4:8] == b"ftyp") or nama.lower().endswith(".mp4")
        if is_mp4 and not nama.lower().endswith(".mp4"):
            nama = nama.rsplit(".", 1)[0] + ".mp4"
        mime = "video/mp4" if is_mp4 else "image/gif"
        return self.panggil(
            "sendAnimation",
            {"chat_id": chat_id, "caption": caption[:1000], "parse_mode": "HTML"},
            files={"animation": (nama, isi, mime)}, timeout=120,
        )

    def kirim_album(self, chat_id: int, daftar_foto: list[tuple[str, bytes]], caption: str = ""):
        """Kirim 2-10 foto sekaligus. Caption ditempel di foto pertama."""
        media, files = [], {}
        for i, (nama, isi) in enumerate(daftar_foto):
            item = {"type": "photo", "media": f"attach://f{i}"}
            if i == 0 and caption:
                item["caption"], item["parse_mode"] = caption[:1000], "HTML"
            media.append(item)
            files[f"f{i}"] = (nama, isi)
        return self.panggil("sendMediaGroup", {"chat_id": chat_id, "media": json.dumps(media)},
                            files=files, timeout=120)


class Pengirim(threading.Thread):
    """Antrean kirim di belakang layar.

    Kalau internet putus, pesan dicoba ulang terus (jeda makin lama, maksimal 60 detik)
    sampai terkirim atau umurnya lewat 30 menit. Loop pemantauan tidak ikut macet.
    """

    UMUR_MAKS = 30 * 60

    def __init__(self, log):
        super().__init__(daemon=True, name="pengirim")
        self.log = log
        # Antrean berprioritas: hasil DPS (penting) selalu dikirim duluan,
        # walaupun ada peringatan lain yang sedang dicoba ulang.
        self.antrean: queue.PriorityQueue = queue.PriorityQueue()
        self.ada_baru = threading.Event()
        self._urut = 0
        self._kunci = threading.Lock()

    def tambah(self, keterangan: str, fungsi, *args, penting: bool = False):
        with self._kunci:
            self._urut += 1
            urut = self._urut
        self.antrean.put((0 if penting else 1, urut, time.time(), 1.0, keterangan, fungsi, args))
        self.ada_baru.set()

    def run(self):
        while True:
            prio, urut, dibuat, jeda, keterangan, fungsi, args = self.antrean.get()
            mulai = time.time()
            try:
                fungsi(*args)
                self.log.info("Terkirim '%s' (%.1f detik)", keterangan, time.time() - mulai)
            except TelegramSementara as e:
                if time.time() - dibuat > self.UMUR_MAKS:
                    self.log.error("Batal kirim '%s' (sudah 30 menit gagal): %s", keterangan, e)
                    continue
                tunggu = max(jeda, e.tunggu)
                self.log.warning("Gagal kirim '%s' (%s). Coba lagi %d detik lagi.", keterangan, e, tunggu)
                # Tunggu, tapi bangun lebih cepat kalau ada pesan baru (mungkin lebih penting).
                self.ada_baru.clear()
                self.ada_baru.wait(tunggu)
                self.antrean.put((prio, urut, dibuat, min(jeda * 2, 30), keterangan, fungsi, args))
            except TelegramError as e:
                self.log.error("Telegram menolak '%s': %s", keterangan, e)
            except Exception:
                self.log.exception("Error tak terduga saat kirim '%s'", keterangan)
