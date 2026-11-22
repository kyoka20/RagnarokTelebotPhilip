# File game Ragnarok: The New World (hasil cek 2026-11-22)

Lokasi di PC ini: `C:\Users\pemil\AppData\Roaming\gnjoy\roworldsea\Ragnarok The New World\v6\roworld\` (~30 GB, publisher gnjoy SEA).

## Isi
- Engine Unity 2022.3 + IL2CPP (`GameAssembly.dll`) + HybridCLR hot-update + anti-cheat Tencent ACE (`AntiCheatExpert/`).
- Logika game (skill, UI, stat) ditulis di **Lua** (tolua). C# hanya tampilan angka damage (`DamageFloaterManager`).
- `game_Data/PersistentData/Assemblies/HotUpdateAssemblies/*.dll.bytes`: header `CDPH`, isi terenkripsi (hanya nama kelas/path terbaca).
- `game_Data/StreamingAssets/AB/**` & `PersistentData/Remote/**/*.bundle`: header `ÿOdin` (UnityFS yang dimodifikasi), isi sebagian besar terenkripsi/terkompres. Tidak ada teks Lua polos.
- `patchSetting.json`, `hotUpdateAssemblyInfo.json`, `catalog_2.bin`: terenkripsi (base64/ biner acak).

## Hasil REA statis (22/11/2026, game & launcher ditutup)
- `global-metadata.dat` (19 MB): header `DA FE 57 13` (normal `AF 1B B1 FA`) → diacak; REA `inspect_il2cpp_metadata` menolak. Sebagian huruf nama masih tembus (cari pakai regex longgar). Tidak didekripsi.
- `GameAssembly.dll` (99 MB): TIDAK dipaket (entropi 6,5; 386 export). Tanpa metadata semua fungsi tak bernama → Ghidra tidak dijalankan (makan jam, hasil tanpa nama).
- String polos berguna di DLL: nama generik HybridCLR `Assembly-CSharp:<kelas>` (99 kelas; hanya `DamageFloaterQueue` soal damage).
- `StreamingAssets/aa/AddressablesLink/link.xml` polos: 890 nama tipe; soal damage hanya UI (`DamageTextAnimation*`). Ada `Luban.*` → tabel config dibuat dengan Luban.
- `Assembly-CSharp` (logika game) = hot-update `CDPH` terenkripsi; `catalog*.bin` header `SGCT`; `SoundbanksInfo.json/xml` polos (nama suara saja).
- Hasil untuk rumus: [[rumus-damage]].

## Kesimpulan
- Tidak ada tabel rumus/skill/enchant yang bisa dibaca langsung. Membukanya = membongkar enkripsi game dilindungi anti-cheat (melanggar ToS, risiko akun Philip). Tidak dilakukan.
- Rumus damage MMO dihitung di server; data akurat lebih aman didapat dari uji DPS nyata lewat bot (lihat [[update-jarak-jauh]]) + data komunitas.

## Skill REA (dipasang 2026-11-22)
- `.claude/skills/reverse-engineer-anything/` (dari github.com/morluto/rea).
- Paket `rea-agents` 6.10.1 (npm global) jalan pakai Node portabel `C:/Users/pemil/tools/node24/node.exe` (Node global 22.13 terlalu lama).
- MCP `rea` didaftarkan scope local proyek ini (`claude mcp get rea`). Cek kesehatan: `node24/node.exe <npm root -g>/rea-agents/scripts/rea.mjs doctor`.
- Mesin analisis: Ghidra 12.2 di `C:/Users/pemil/tools/ghidra` + JDK 25 (Temurin) di `C:/Users/pemil/tools/jdk25`, dipasang lewat env MCP `GHIDRA_INSTALL_DIR` & `JAVA_HOME` (doctor: ghidra healthy). Hopper/IDA tidak dipasang.
- Aturan: hanya analisis statis file di disk, game ditutup, tanpa mengakali anti-cheat.
- Catatan: file terenkripsi (ACE, ToS) membatasi hasil. Rumus tetap dicocokkan dengan uji DPS (lihat [[rumus-damage]]).
