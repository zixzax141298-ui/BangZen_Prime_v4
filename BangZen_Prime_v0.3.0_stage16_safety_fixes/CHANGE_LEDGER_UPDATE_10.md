# CHANGE LEDGER UPDATE 10 — Item 8: pasang untuk Termux dan VPS (paper only)

## Ditambahkan
- `scripts/install_vps.sh`: pemasangan di VPS Linux tanpa Docker dan tanpa paket native.
  Menolak root, menolak jalan di luar folder proyek, menolak path berisi spasi atau `|`,
  menolak Python di bawah 3.11, dan menolak `.env` yang mengaktifkan live atau broadcast
  (fail-closed, sebelum venv dibuat). Memasang ke venv, memverifikasi versi `0.3.0`, lalu
  merender unit ke `deploy/generated/`. Tidak memakai sudo dan tidak mengaktifkan service.
- `scripts/run_monitor_profile.sh`: runner monitor dengan profil `termux_light` atau
  `vps_default`. Menolak profil tak dikenal (exit 2), menolak jika `bangzen-prime` tidak
  ada di PATH, dan menolak watchlist yang melebihi batas profil sebelum menjalankan apa pun.
- `deploy/systemd/bangzen-prime-monitor.service`: template unit (placeholder `__APP_USER__`,
  `__APP_DIR__`, `__VENV_DIR__`). Restart on-failure, KillSignal SIGINT, MemoryMax 512M,
  dan pengerasan dasar (NoNewPrivileges, ProtectSystem=strict, ProtectHome=read-only).
- `deploy/profiles/vps_default.env` (interval 60 s, 20 scan/menit, maks 100 mint) dan
  `deploy/profiles/termux_light.env` (interval 300 s, 5 scan/menit, maks 25 mint).
- `tests/unit/test_deploy_artifacts.py` (17 tes, hanya pustaka standar).

## Diubah
- `docs/TERMUX.md`: path watchlist diperbaiki dari `config/` ke `configs/` (path lama tidak ada).
  Ditambahkan bagian profil ringan Termux, ditandai BELUM DIVERIFIKASI di perangkat.

## Bug yang ditemukan dan diperbaiki
- Template unit awalnya menaruh `StartLimitIntervalSec` dan `StartLimitBurst` di `[Service]`.
  `systemd-analyze verify` melaporkan kunci itu diabaikan. Dipindahkan ke `[Unit]`, dan tes
  `test_start_limit_keys_sit_in_unit_section` mengunci penempatannya.
- Tes awal terlalu lebar: memeriksa kata "docker" dan "sudo" di seluruh teks skrip, padahal
  kata itu muncul di komentar dan pesan instruksi yang hanya dicetak. Tes diubah agar hanya
  memeriksa baris eksekusi. Ini koreksi tes karena tes salah, bukan perubahan ekspektasi
  untuk meloloskan kegagalan nyata.

## Hasil
- `scripts/run_tests.py`: TIDAK DIJALANKAN di sandbox ini. Precheck gagal karena `httpx`
  tidak terpasang dan sandbox tidak punya akses jaringan untuk `pip install`. Precheck
  sengaja menghentikan eksekusi dan tidak diakali. Angka 999 dari tahap sebelumnya tidak
  bisa diverifikasi ulang di sini.
- `python3 -m unittest tests/unit/test_deploy_artifacts.py`: 17 lulus, 0 gagal.
- `tests/unit/test_ci_profiles.py` dan `test_ci_gate.py`: 32 lulus, 0 gagal.
- `bash -n` pada kedua skrip baru: bersih.
- `systemd-analyze verify` pada unit yang dirender (dengan stub binary sementara di `/opt`,
  yang sudah dihapus): exit 0.
- Uji jalur gagal `install_vps.sh` sebagai user non-root: di luar folder proyek ditolak;
  `.env` dengan `BANGZEN_LIVE_TRADING=true`, `BANGZEN_BROADCAST_ENABLED="yes"`, dan
  `  BANGZEN_LIVE_TRADING = 1  ` semuanya ditolak, dan venv tidak dibuat.
- `compileall` pada file tes baru: bersih.
- `scripts/check_unused_imports.py`: file baru bersih. Ada temuan lama di
  `strategies/__init__.py`, `core/interfaces/dashboard.py`, dan `tests/e2e/test_v3_flow.py`.
  Itu tidak disentuh tahap ini.

## Tidak berubah
- AI_RULES.yaml, RULES.md, SECURITY.md (termasuk RT-06).
- Live dan broadcast tetap ditolak di `core/config.py`.
- Bobot strategi, RSI period, threshold, dan readiness gate tidak disentuh.
- Tidak ada signing, private key, atau broadcast.

## BELUM DIVERIFIKASI
- Pemasangan nyata di Termux (`pkg install`, `pip install .`, perilaku `run_monitor_profile.sh`).
- Pemasangan nyata di VPS, termasuk `systemctl enable --now` dan perilaku restart.
- Nilai profil `termux_light` dan `MemoryMax=512M` belum diukur. Keduanya pilihan awal.
- Menjaga proses Termux tetap hidup (tmux atau termux-wake-lock) belum diuji.
- Sandbox memakai Python 3.12.3; proyek menargetkan 3.13. Belum diuji di 3.13.
- Wheel tidak diuji ulang di tahap ini. Verifikasi wheel menyertakan `*.sql` masih item 5.

## Batasan yang tersisa
- Suite penuh harus dijalankan ulang di lingkungan dengan `httpx` dan `defusedxml` terpasang.
- Skrip `install_vps.sh` belum pernah berhasil sampai langkah pip di sandbox (tidak ada jaringan).
- Keputusan owner yang masih terbuka: apakah unit systemd boleh diaktifkan otomatis (saat ini
  tidak), dan apakah nilai profil perlu disesuaikan setelah pengukuran di perangkat.
