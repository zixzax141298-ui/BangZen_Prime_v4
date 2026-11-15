# CHANGE LEDGER UPDATE 11 — Item 9: laporan harian dan Telegram dengan deduplikasi (paper only)

## Ditambahkan
- `bangzen_prime/storage/migrations/0007_notification_delivery.sql`: tabel `daily_reports`
  (isi laporan dibekukan per hari UTC) dan `notification_deliveries` (ledger dedup dengan status
  PENDING, SENDING, SENT, FAILED, plus lease).
- `bangzen_prime/storage/deliveries.py`: `DeliveryStore` dengan `claim`, `mark_sent`,
  `mark_failed`, dan `status`. Klaim memakai UPDATE bersyarat, jadi hanya satu pemanggil yang menang
  dalam satu lease. Timestamp memakai format tetap agar pembanding SQL benar.
- `bangzen_prime/notifications/daily_report.py`: `build_body`, `freeze_report`, `chunk_body`,
  dan `send_daily_report`. Laporan hanya untuk hari UTC yang sudah selesai. Pengiriman per saluran
  berhenti di kegagalan pertama, saluran lain tetap jalan, dan error yang disimpan disanitasi.
- `docs/DAILY_REPORT.md`: pemakaian dan semantik at-least-once.
- `tests/unit/test_daily_report.py`: 24 tes.

## Diubah
- `bangzen_prime/core/interfaces/cli.py`: subcommand `daily-report` (`--day`, `--send`).
  Tanpa `--send` hanya mencetak, tanpa jaringan dan tanpa ledger. Dengan `--send`, mode dan
  konfigurasi Telegram diperiksa lebih dulu. Subcommand ini tidak masuk daftar perintah yang
  diblokir saat halt, karena tidak membuka atau mengubah posisi.
- Ekspektasi jumlah migrasi diperbarui dari 6 ke 7 (konsekuensi yang disengaja dari 0007):
  `tests/integration/test_persistence.py` (3 tempat), `tests/e2e/test_scan_flow.py` (1),
  `tests/e2e/test_cli.py` (2).

## Hasil
- `python3 -m unittest tests/unit/test_daily_report.py`: 24 lulus, 0 gagal, juga dengan
  `-W error::ResourceWarning`.
- `tests/integration/test_persistence.py`: 22 lulus, 0 gagal (setelah ekspektasi 7).
- `scripts/run_tests.py`: TIDAK DIJALANKAN. Precheck masih gagal karena `httpx` belum terpasang
  dan sandbox tidak punya jaringan. Tes berikut mengimpor bootstrap, yang membutuhkan `httpx`,
  sehingga juga TIDAK DIJALANKAN di sini: `tests/e2e/test_scan_flow.py`, `tests/e2e/test_cli.py`,
  dan `tests/unit/test_forward_runner.py`. Ekspektasi versi migrasi di ketiganya sudah diperbarui
  tetapi belum dijalankan.
- `check_unused_imports.py`: berkas baru dan berkas yang diubah bersih. Temuan lama tidak berubah.
- `compileall` untuk `bangzen_prime` dan `tests`: bersih.

## Tidak berubah
- AI_RULES.yaml, RULES.md, SECURITY.md, termasuk RT-06.
- Live dan broadcast tetap ditolak di `core/config.py`. Tidak ada signing atau broadcast.
- Bobot strategi, RSI period, threshold, dan readiness gate.
- Laporan tidak memuat PnL atau angka profit.

## BELUM DIVERIFIKASI
- Pengiriman nyata ke Telegram, termasuk tingkah laku rate-limit dan respons API sungguhan.
- Duplikat nyata saat proses dihentikan di antara kirim dan SENT. Dokumentasi menyatakan ini,
  tetapi belum diuji dengan proses yang benar-benar dibunuh.
- Dua proses yang berjalan bersamaan. Klaim berlease sudah menjaga kasus ini secara logika,
  tetapi belum diuji lintas proses.
- Penjadwalan laporan harian (timer systemd atau cron). Belum dibuat.

## Batasan yang tersisa
- Dedup belum mencakup notifikasi signal. Signal tetap memakai outbox at-least-once.
- Sebagian tes yang dipengaruhi migrasi belum bisa dijalankan tanpa `httpx`.
- Sandbox memakai Python 3.12.3. Proyek menargetkan 3.13.

## Keputusan owner yang masih dibutuhkan
- Apakah laporan harian perlu dijadwalkan otomatis, dan jam berapa (UTC).
- Apakah dedup signal ikut dipindah ke ledger ini, atau cukup outbox yang sudah ada.
