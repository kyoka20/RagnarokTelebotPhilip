"""Membuat file Excel arsip pemain (.xlsx) yang rapi untuk perintah /arsip.

Sheet 1 "Ringkasan"   : kotak angka penting + tabel semua pemain.
Sheet 2 "Riwayat Test": semua hasil test DPS dari semua pemain.
"""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

# Warna
NAVY = "1F2A44"
EMAS = "C9A227"
ABU_TEKS = "6B7280"
GARIS = "D9DEE7"
KOTAK = "F3F5F9"
HIJAU, HIJAU_MUDA = "1E7B4A", "E3F4EA"
MERAH, MERAH_MUDA = "B42318", "FDE8E7"
KUNING, KUNING_MUDA = "8A6100", "FFF4D6"

FONT = "Segoe UI"
TIPIS = Side(style="thin", color=GARIS)
KOTAK_GARIS = Border(left=TIPIS, right=TIPIS, top=TIPIS, bottom=TIPIS)
TENGAH = Alignment(horizontal="center", vertical="center")
KIRI = Alignment(horizontal="left", vertical="center", indent=1)
KANAN = Alignment(horizontal="right", vertical="center", indent=1)


def _isi(warna: str) -> PatternFill:
    return PatternFill("solid", start_color=warna, end_color=warna)


def _angka(v):
    try:
        return int(str(v).replace(".", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _judul(ws, teks: str, sub: str, lebar: int) -> None:
    akhir = get_column_letter(lebar)
    for baris, tinggi in ((1, 8), (2, 34), (3, 20), (4, 8)):
        ws.row_dimensions[baris].height = tinggi
        for k in range(1, lebar + 1):
            ws.cell(baris, k).fill = _isi(NAVY)
    ws.merge_cells(f"A2:{akhir}2")
    ws.merge_cells(f"A3:{akhir}3")
    ws["A2"] = teks
    ws["A2"].font = Font(name=FONT, size=18, bold=True, color="FFFFFF")
    ws["A2"].alignment = KIRI
    ws["A3"] = sub
    ws["A3"].font = Font(name=FONT, size=10, color="C8CEDB")
    ws["A3"].alignment = KIRI
    for k in range(1, lebar + 1):  # garis emas di bawah judul
        ws.cell(5, k).fill = _isi(EMAS)
    ws.row_dimensions[5].height = 3


def _kotak_angka(ws, baris: int, kolom: int, lebar: int, label: str, nilai, format_: str = "General") -> None:
    a, b = get_column_letter(kolom), get_column_letter(kolom + lebar - 1)
    ws.merge_cells(f"{a}{baris}:{b}{baris}")
    ws.merge_cells(f"{a}{baris + 1}:{b}{baris + 1}")
    for r in (baris, baris + 1):
        for k in range(kolom, kolom + lebar):
            c = ws.cell(r, k)
            c.fill = _isi(KOTAK)
            c.border = Border(left=TIPIS if k == kolom else None, right=TIPIS if k == kolom + lebar - 1 else None,
                              top=Side(style="medium", color=EMAS) if r == baris else None,
                              bottom=TIPIS if r == baris + 1 else None)
    c = ws.cell(baris, kolom, label.upper())
    c.font = Font(name=FONT, size=8, bold=True, color=ABU_TEKS)
    c.alignment = Alignment(horizontal="center", vertical="bottom")
    c = ws.cell(baris + 1, kolom, nilai)
    c.font = Font(name=FONT, size=16, bold=True, color=NAVY)
    c.alignment = Alignment(horizontal="center", vertical="top")
    c.number_format = format_


def _tabel(ws, nama: str, baris_awal: int, kolom: list[tuple], data: list[list], gaya="TableStyleLight9"):
    """kolom = [(judul, lebar, format, perataan)]."""
    for k, (judul, lebar, _, _) in enumerate(kolom, 1):
        ws.column_dimensions[get_column_letter(k)].width = lebar
        c = ws.cell(baris_awal, k, judul)
        c.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
        c.fill = _isi(NAVY)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = KOTAK_GARIS
    ws.row_dimensions[baris_awal].height = 30
    for i, isi in enumerate(data):
        r = baris_awal + 1 + i
        ws.row_dimensions[r].height = 22
        for k, (v, (_, _, fmt, rata)) in enumerate(zip(isi, kolom), 1):
            c = ws.cell(r, k, v)
            c.font = Font(name=FONT, size=10, color="1F2937")
            c.number_format = fmt
            c.alignment = rata
            c.border = KOTAK_GARIS
    akhir = baris_awal + max(len(data), 1)
    if not data:  # tabel Excel butuh minimal satu baris
        for k in range(1, len(kolom) + 1):
            ws.cell(akhir, k).border = KOTAK_GARIS
    ref = f"A{baris_awal}:{get_column_letter(len(kolom))}{akhir}"
    t = Table(displayName=nama, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name=gaya, showRowStripes=True)
    ws.add_table(t)
    return akhir


def _sheet_ringkasan(ws, pemain: list[dict], catatan_kaki: str) -> None:
    kolom = [
        ("No", 5, "0", TENGAH),
        ("ID Game", 13, "@", TENGAH),
        ("Nick", 18, "@", KIRI),
        ("Job", 14, "@", KIRI),
        ("Kontak", 16, "@", KIRI),
        ("Paket", 14, "@", KIRI),
        ("Bayar", 13, "@", TENGAH),
        ("Tgl Order", 12, "dd mmm yyyy", TENGAH),
        ("Target DPS", 14, "#,##0", KANAN),
        ("DPS Awal", 14, "#,##0", KANAN),
        ("DPS Terbaik", 14, "#,##0", KANAN),
        ("DPS Terakhir", 14, "#,##0", KANAN),
        ("Kenaikan", 11, "+0.0%;-0.0%;0.0%", TENGAH),
        ("Progres Target", 14, "0%", TENGAH),
        ("Jumlah Test", 9, "0", TENGAH),
        ("Test Terakhir", 17, "dd mmm yyyy hh:mm", TENGAH),
        ("Catatan", 30, "@", Alignment(horizontal="left", vertical="center", indent=1, wrap_text=True)),
    ]
    _judul(ws, "ARSIP PEMAIN · JASA BUILD DPS",
           f"Dibuat {datetime.now():%d %B %Y, %H:%M}" + (f"   ·   {catatan_kaki}" if catatan_kaki else ""),
           len(kolom))

    # Kotak angka penting (baris 7-8)
    lunas = sum(1 for p in pemain if (p["bayar"] or "").lower() == "lunas")
    capai = sum(1 for p in pemain if p["progres"] is not None and p["progres"] >= 1)
    naik = [p["naik"] for p in pemain if p["naik"] is not None]
    ws.row_dimensions[6].height = 12
    ws.row_dimensions[7].height = 20
    ws.row_dimensions[8].height = 30
    _kotak_angka(ws, 7, 2, 3, "Total pemain", len(pemain))
    _kotak_angka(ws, 7, 6, 3, "Sudah lunas", f"{lunas} / {len(pemain)}")
    _kotak_angka(ws, 7, 10, 3, "Target tercapai", f"{capai} / {len(pemain)}")
    _kotak_angka(ws, 7, 14, 3, "Rata-rata kenaikan",
                 sum(naik) / len(naik) if naik else "-", "+0.0%;-0.0%;0.0%")
    ws.row_dimensions[9].height = 14

    awal = 10
    data = [[n, p["id"], p["nick"], p["job"], p["kontak"], p["paket"], p["bayar"], p["tgl_order"],
             p["target"], p["awal"], p["terbaik"], p["terakhir"], p["naik"], p["progres"], p["jumlah"],
             p["test_terakhir"], p["catatan"]] for n, p in enumerate(pemain, 1)]
    akhir = _tabel(ws, "TabelPemain", awal, kolom, data)

    if pemain:
        r1 = awal + 1
        # Bayar: hijau / kuning / merah
        for teks, f_, b_ in (("Lunas", HIJAU, HIJAU_MUDA), ("DP", KUNING, KUNING_MUDA),
                             ("Belum bayar", MERAH, MERAH_MUDA)):
            ws.conditional_formatting.add(
                f"G{r1}:G{akhir}", CellIsRule(operator="equal", formula=[f'"{teks}"'],
                                             font=Font(name=FONT, bold=True, color=f_), fill=_isi(b_)))
        # Kenaikan: hijau kalau naik, merah kalau turun
        ws.conditional_formatting.add(f"M{r1}:M{akhir}", CellIsRule(
            operator="greaterThan", formula=["0"], font=Font(name=FONT, bold=True, color=HIJAU)))
        ws.conditional_formatting.add(f"M{r1}:M{akhir}", CellIsRule(
            operator="lessThan", formula=["0"], font=Font(name=FONT, bold=True, color=MERAH)))
        # Progres target: bar emas, tulisan hijau kalau sudah 100%
        ws.conditional_formatting.add(f"N{r1}:N{akhir}", DataBarRule(
            start_type="num", start_value=0, end_type="num", end_value=1, color=EMAS, showValue=True))
        ws.conditional_formatting.add(f"N{r1}:N{akhir}", CellIsRule(
            operator="greaterThanOrEqual", formula=["1"], font=Font(name=FONT, bold=True, color=HIJAU)))
        for r in range(r1, akhir + 1):  # DPS terbaik ditebalkan
            ws.cell(r, 11).font = Font(name=FONT, size=10, bold=True, color=NAVY)

    r = akhir + 2
    ws.cell(r, 1, "Kenaikan = DPS terbaik dibanding DPS awal.  Progres target = DPS terbaik ÷ target.").font = \
        Font(name=FONT, size=9, italic=True, color=ABU_TEKS)
    ws.freeze_panes = ws.cell(awal + 1, 4)  # judul tabel + No/ID/Nick tetap terlihat saat digulir
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90
    _cetak(ws, f"A1:{get_column_letter(len(kolom))}{r}", awal)


def _sheet_riwayat(ws, riwayat: list[dict]) -> None:
    kolom = [
        ("No", 6, "0", TENGAH),
        ("Waktu Test", 19, "dd mmm yyyy hh:mm:ss", TENGAH),
        ("Nick", 18, "@", KIRI),
        ("ID Game", 13, "@", TENGAH),
        ("Job", 14, "@", KIRI),
        ("DPS", 15, "#,##0", KANAN),
        ("Total Damage", 17, "#,##0", KANAN),
        ("Rekor", 15, "#,##0", KANAN),
        ("Rekor Baru?", 12, "@", TENGAH),
    ]
    _judul(ws, "RIWAYAT TEST DPS", f"{len(riwayat)} test dari semua pemain, terbaru di atas", len(kolom))
    data = [[n, h["waktu"], h["nick"], h["id"], h["job"], h["dps"], h["total"], h["rekor"],
             h["rekor_baru"]] for n, h in enumerate(riwayat, 1)]
    awal = 7
    ws.row_dimensions[6].height = 12
    akhir = _tabel(ws, "TabelRiwayat", awal, kolom, data)
    if riwayat:
        ws.conditional_formatting.add(f"I{awal + 1}:I{akhir}", CellIsRule(
            operator="equal", formula=['"★ Ya"'], font=Font(name=FONT, bold=True, color=KUNING),
            fill=_isi(KUNING_MUDA)))
        ws.conditional_formatting.add(f"I{awal + 1}:I{akhir}", CellIsRule(
            operator="equal", formula=['"Awal"'], font=Font(name=FONT, italic=True, color=ABU_TEKS)))
        for r in range(awal + 1, akhir + 1):
            ws.cell(r, 6).font = Font(name=FONT, size=10, bold=True, color=NAVY)
    ws.freeze_panes = ws.cell(awal + 1, 1)
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90
    _cetak(ws, f"A1:{get_column_letter(len(kolom))}{akhir}", awal)


def _cetak(ws, area: str, baris_judul: int) -> None:
    ws.print_area = area
    ws.print_title_rows = f"{baris_judul}:{baris_judul}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.oddFooter.center.text = "Halaman &P dari &N"


def buat(daftar: list[tuple[str, dict, list[dict]]], catatan_kaki: str = "") -> bytes:
    """daftar = [(pid, profil, semua hasil test ok urut lama->baru)]. Hasil: isi file .xlsx."""
    pemain, riwayat = [], []
    for pid, p, hasil in daftar:
        nick = p.get("nick") or p.get("nama") or pid
        id_game = str(p.get("id_game") or "")
        target = _angka(p.get("target"))
        awal = hasil[0]["dps"] if hasil else None
        terbaik = max(h["dps"] for h in hasil) if hasil else None
        try:
            tgl = datetime.strptime(p.get("tanggal_order") or "", "%Y-%m-%d")
        except ValueError:
            tgl = p.get("tanggal_order") or None
        pemain.append({
            "id": id_game, "nick": nick, "job": p.get("job") or "",
            "kontak": str(p.get("kontak") or ""), "paket": p.get("paket") or "",
            "bayar": p.get("bayar") or "", "tgl_order": tgl, "target": target,
            "awal": awal, "terbaik": terbaik, "terakhir": hasil[-1]["dps"] if hasil else None,
            "naik": (terbaik - awal) / awal if awal else None,
            "progres": terbaik / target if terbaik and target else None,
            "jumlah": len(hasil), "test_terakhir": hasil[-1]["waktu"] if hasil else None,
            "catatan": p.get("catatan") or "",
        })
        puncak = 0
        for h in hasil:
            riwayat.append({"waktu": h["waktu"], "nick": nick, "id": id_game, "job": p.get("job") or "",
                            "dps": h["dps"], "total": h.get("total"), "rekor": h.get("rekor"),
                            "rekor_baru": "Awal" if puncak == 0 else ("★ Ya" if h["dps"] > puncak else "")})
            puncak = max(puncak, h["dps"])
    riwayat.sort(key=lambda h: h["waktu"], reverse=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Ringkasan"
    ws.sheet_properties.tabColor = NAVY
    _sheet_ringkasan(ws, pemain, catatan_kaki)
    ws2 = wb.create_sheet("Riwayat Test")
    ws2.sheet_properties.tabColor = EMAS
    _sheet_riwayat(ws2, riwayat)
    wb.properties.title = "Arsip Pemain - Jasa Build DPS"
    wb.properties.creator = "Bot DPS"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
