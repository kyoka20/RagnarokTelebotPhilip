"""/cek_laptop - cari pelaku yang bikin laptop lemot (tanpa modul tambahan).

Pakai PowerShell bawaan Windows: ukur CPU tiap proses selama 2 detik, RAM,
disk, baterai/mode hemat daya, kecepatan CPU (throttle), bot dobel, dan
program autostart. Hasil berupa teks HTML pendek untuk Telegram.
"""
from __future__ import annotations

import html
import json
import os
import subprocess

_PS = r"""
$ErrorActionPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$n=[Environment]::ProcessorCount
$a=@{}; Get-Process | ForEach-Object { $a[$_.Id]=$_.TotalProcessorTime.TotalMilliseconds }
Start-Sleep -Milliseconds 2000
$p=Get-Process | Where-Object { $_.Id -ne 0 } | ForEach-Object {
  $c=0; if($a.ContainsKey($_.Id)){ $c=($_.TotalProcessorTime.TotalMilliseconds-$a[$_.Id])/20/$n }
  [pscustomobject]@{n=$_.ProcessName;id=$_.Id;c=[math]::Round($c,1);m=[math]::Round($_.WorkingSet64/1MB)} }
$os=Get-CimInstance Win32_OperatingSystem
$cpu=(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average
$perf=(Get-CimInstance Win32_PerfFormattedData_Counters_ProcessorInformation -Filter "Name='_Total'").PercentProcessorPerformance
$disk=(Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter "Name='_Total'").PercentDiskTime
$py=@(Get-CimInstance Win32_Process -Filter "Name like 'python%'" | ForEach-Object { [pscustomobject]@{id=$_.ProcessId;cmd=[string]$_.CommandLine} })
$st=@(Get-CimInstance Win32_StartupCommand | ForEach-Object { [string]$_.Name })
$c=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$b=Get-CimInstance Win32_Battery | Select-Object -First 1
$plan=(powercfg /getactivescheme) -join ' '
[pscustomobject]@{proc=$p;ramTot=$os.TotalVisibleMemorySize;ramFree=$os.FreePhysicalMemory;cpu=$cpu;perf=$perf;disk=$disk;
 py=$py;start=$st;upDays=[math]::Round(((Get-Date)-$os.LastBootUpTime).TotalDays,1);cFree=$c.FreeSpace;cSize=$c.Size;
 batStat=$b.BatteryStatus;batPct=$b.EstimatedChargeRemaining;plan=$plan} | ConvertTo-Json -Depth 3 -Compress
"""


def _ambil() -> dict:
    hasil = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS],
        capture_output=True, timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    teks = hasil.stdout.decode("utf-8", errors="replace").strip()
    awal = teks.find("{")
    if awal < 0:
        raise RuntimeError("PowerShell tidak memberi hasil: " + hasil.stderr.decode("utf-8", "replace")[:200])
    return json.loads(teks[awal:])


def _gb(kb_or_b, satuan_kb: bool) -> float:
    v = float(kb_or_b or 0)
    return v / (1024 ** 2) if satuan_kb else v / (1024 ** 3)


def diagnosa(pid_bot: int | None = None) -> str:
    pid_bot = pid_bot or os.getpid()
    d = _ambil()
    procs = d.get("proc") or []
    if isinstance(procs, dict):
        procs = [procs]

    # Gabung proses bernama sama (mis. chrome banyak tab).
    gabung: dict[str, list[float]] = {}
    bot_c = bot_m = 0.0
    for p in procs:
        nama = str(p.get("n") or "?")
        if nama.lower() == "idle":
            continue
        c, m = float(p.get("c") or 0), float(p.get("m") or 0)
        if p.get("id") == pid_bot:
            bot_c, bot_m = c, m
            nama = f"{nama} (BOT RO)"
        g = gabung.setdefault(nama, [0.0, 0.0, 0])
        g[0] += c
        g[1] += m
        g[2] += 1

    ram_tot = _gb(d.get("ramTot"), True)
    ram_pakai = ram_tot - _gb(d.get("ramFree"), True)
    ram_pct = ram_pakai / ram_tot * 100 if ram_tot else 0
    cpu = float(d.get("cpu") or 0)
    perf = d.get("perf")
    disk = float(d.get("disk") or 0)
    c_free, c_size = _gb(d.get("cFree"), False), _gb(d.get("cSize"), False)

    # Bot RO dobel?
    py = d.get("py") or []
    if isinstance(py, dict):
        py = [py]
    bot_jalan = [x for x in py if "bot.py" in str(x.get("cmd") or "").lower()]

    temuan: list[str] = []
    if len(bot_jalan) > 1:
        temuan.append(f"🔴 <b>Bot RO jalan {len(bot_jalan)}x sekaligus</b> (dobel) → matikan semua lalu nyalakan 1x.")
    if cpu >= 80:
        temuan.append(f"🔴 CPU penuh ({cpu:.0f}%).")
    if ram_pct >= 85:
        temuan.append(f"🔴 RAM hampir habis ({ram_pct:.0f}%) → laptop pakai disk sebagai RAM, jadi lambat.")
    if disk >= 80:
        temuan.append(f"🔴 Disk sibuk {disk:.0f}% (sering karena Windows Update / antivirus / RAM penuh).")
    if c_size and c_free / c_size < 0.1:
        temuan.append(f"🟠 Disk C hampir penuh (sisa {c_free:.0f} GB).")
    try:
        if perf is not None and float(perf) < 60:
            temuan.append(f"🟠 CPU diperlambat ke {float(perf):.0f}% kecepatan (panas / mode hemat baterai).")
    except (TypeError, ValueError):
        pass
    bat = d.get("batStat")
    if bat == 1:
        temuan.append(f"🟠 Laptop pakai <b>baterai</b> ({d.get('batPct')}%), tidak dicolok → Windows sering memperlambat CPU.")
    plan = str(d.get("plan") or "")
    if "saver" in plan.lower() or "hemat" in plan.lower():
        temuan.append("🟠 Mode daya = Hemat Daya (Power saver).")
    up = float(d.get("upDays") or 0)
    if up >= 7:
        temuan.append(f"🟡 Laptop belum restart {up:.0f} hari → coba restart sekali.")
    berat = {k.lower(): v for k, v in gabung.items()}
    for kunci, label in (("msmpeng", "Windows Defender sedang scan"),
                         ("tiworker", "Windows Update sedang memasang"),
                         ("trustedinstaller", "Windows Update sedang memasang"),
                         ("searchindexer", "Windows Search sedang mengindeks file"),
                         ("compattelrunner", "Telemetri Windows sedang jalan")):
        v = berat.get(kunci)
        if v and v[0] >= 8:
            temuan.append(f"🟠 {label} ({v[0]:.0f}% CPU) — biasanya sementara.")

    vonis = ("✅ Bot RO ringan, bukan pelakunya." if bot_c < 10 and bot_m < 450
             else "⚠️ Bot RO sedang lumayan berat.")
    b = [
        "🩺 <b>CEK LAPTOP</b>",
        f"CPU <b>{cpu:.0f}%</b> | RAM <b>{ram_pakai:.1f}/{ram_tot:.1f} GB ({ram_pct:.0f}%)</b> | Disk sibuk <b>{disk:.0f}%</b>",
        f"Bot RO: CPU <b>{bot_c:.1f}%</b>, RAM <b>{bot_m:.0f} MB</b> → {vonis}",
        "",
        "<b>Temuan:</b>",
    ]
    b += [f"• {t}" for t in temuan] or ["• Tidak ada yang mencurigakan saat ini."]
    b.append("\n🔥 <b>Top CPU (2 detik):</b>")
    for k, (c, m, n) in sorted(gabung.items(), key=lambda x: -x[1][0])[:7]:
        b.append(f"• {html.escape(k)}{f' ×{int(n)}' if n > 1 else ''}: <b>{c:.1f}%</b> ({m:.0f} MB)")
    b.append("\n🧠 <b>Top RAM:</b>")
    for k, (c, m, n) in sorted(gabung.items(), key=lambda x: -x[1][1])[:7]:
        b.append(f"• {html.escape(k)}{f' ×{int(n)}' if n > 1 else ''}: <b>{m:.0f} MB</b>")
    st = d.get("start") or []
    if isinstance(st, str):
        st = [st]
    if st:
        b.append("\n🚀 <b>Ikut nyala saat laptop hidup:</b> " + html.escape(", ".join(str(x) for x in st[:15])))
    if up:
        b.append(f"\n⏱ Nyala sejak {up:.1f} hari lalu")
    return "\n".join(b)


if __name__ == "__main__":
    import re
    print(re.sub(r"<[^>]+>", "", diagnosa()))
