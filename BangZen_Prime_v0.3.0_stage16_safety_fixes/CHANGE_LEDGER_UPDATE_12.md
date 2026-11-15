# CHANGE LEDGER UPDATE 12 — Penjadwalan laporan harian (00:10 UTC, paper only)

## Keputusan owner
- Laporan harian dijadwalkan otomatis. Jam pengiriman 00:10 UTC. Laporan merangkum hari UTC sebelumnya.

## Ditambahkan
- `deploy/systemd/bangzen-prime-daily-report.service`: unit oneshot, menjalankan
  `bangzen-prime daily-report --send`. Tanpa kebijakan restart, supaya kegagalan tidak memicu
  pengiriman berulang di luar jadwal.
- `deploy/systemd/bangzen-prime-daily-report.timer`: `OnCalendar=*-*-* 00:10:00 UTC`,
  `Persistent=true`.
- Tes di `tests/unit/test_deploy_artifacts.py` (4 tes baru): service oneshot dan paper only,
  placeholder standar, timer 00:10 UTC, dan installer merender ketiga unit.

## Diubah
- `scripts/install_vps.sh`: merender monitor, service laporan, dan timer. Perintah pemasangan
  ditampilkan untuk keduanya. Tidak ada yang diaktifkan otomatis.
- `docs/DAILY_REPORT.md`: bagian jadwal dan pemasangan timer.

## Hasil
- `tests/unit/test_deploy_artifacts.py`: 21 lulus, 0 gagal.
- `systemd-analyze calendar "*-*-* 00:10:00 UTC"`: valid. Eksekusi berikutnya 16 Nov 2026 00:10 UTC.
- `systemd-analyze verify` pada service dan timer yang sudah dirender (dengan stub binary
  sementara, sudah dihapus): exit 0.
- `scripts/run_tests.py`: TIDAK DIJALANKAN (`httpx` belum terpasang, tidak ada jaringan).

## BELUM DIVERIFIKASI
- Timer berjalan di VPS nyata, termasuk perilaku `Persistent=true` setelah mati.
- Pengiriman Telegram nyata dari timer.
- Perilaku saat mode operasi melarang Telegram: timer akan gagal setiap hari. Belum diuji di VPS.

## Batasan yang tersisa
- Hari yang terlewat saat VPS mati tidak dikejar. Hanya hari terakhir yang dikirim.
- Dedup signal notification belum dipindah ke ledger. Itu keputusan terpisah (pertanyaan 2 sebelumnya, belum dijawab).
