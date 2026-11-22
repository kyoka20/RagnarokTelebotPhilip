# Penjaga bot: dijalankan Windows Task Scheduler saat login dan tiap 5 menit.
# - Kalau bot tidak sedang jalan -> bot dinyalakan (jendela minimize).
# - Pengaman: kalau bot memakai RAM lebih dari 800 MB (normalnya sekitar 50 MB), bot dimatikan
#   lalu langsung dinyalakan lagi, supaya laptop tidak pernah jadi berat.
$folder = $PSScriptRoot
$log = Join-Path $folder 'log\penjaga.log'
$waktu = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

# Sengaja dimatikan (/matikan atau 9_matikan_bot.bat) -> jangan dinyalakan lagi...
# ...KECUALI laptop sudah restart / login ulang sejak dimatikan: maka tanda dihapus & bot menyala lagi.
# File ini juga hilang sendiri saat bot dinyalakan manual (4_jalankan_bot.bat).
$tanda = Join-Path $folder 'BOT_DIMATIKAN.txt'
if (Test-Path $tanda) {
    # Awal sesi = jam explorer.exe (layar Windows) mulai = jam login. Shutdown dengan "Fast Startup"
    # tidak mengubah jam boot, tapi tetap login ulang, jadi explorer lebih bisa dipercaya.
    $sesi = Get-Process explorer -ErrorAction SilentlyContinue | Sort-Object StartTime | Select-Object -First 1 -ExpandProperty StartTime
    if (-not $sesi) { $sesi = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime }
    if ((Get-Item $tanda).LastWriteTime -lt $sesi) {
        Remove-Item $tanda -Force -ErrorAction SilentlyContinue
        Add-Content -Path $log -Value "$waktu laptop sudah restart/login ulang sejak /matikan -> bot dinyalakan lagi"
    } else {
        exit
    }
}

$bot = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*bot.py*' }
foreach ($p in $bot) {
    $proses = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
    if ($proses -and $proses.WorkingSet64 -gt 800MB) {
        Add-Content -Path $log -Value ("$waktu RAM bot {0:N0} MB (terlalu besar) -> bot dimulai ulang" -f ($proses.WorkingSet64 / 1MB))
        Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -like '*bot.py*' -or $_.CommandLine -like '*4_jalankan_bot.bat*'
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 2
        break
    }
}

$jalan = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like '*bot.py*' -or $_.CommandLine -like '*4_jalankan_bot.bat*'
}
if (-not $jalan) {
    Start-Process -FilePath (Join-Path $folder '4b_jalankan_bot_minimize.bat') -WorkingDirectory $folder -WindowStyle Minimized
    Add-Content -Path $log -Value "$waktu bot tidak jalan -> dinyalakan"
}
