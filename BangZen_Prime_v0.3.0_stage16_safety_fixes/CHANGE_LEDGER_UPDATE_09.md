# CHANGE LEDGER UPDATE 09 — stage 16: CLI forward-paper (paper only)

## Ditambahkan
- `core/forward_runner.py` (baru)
  - `ForwardRunSettings`: watchlist, ledger, interval (min 15 detik), cycles (0 = sampai halt), scans-per-minute (min 1), usia sinyal maksimum (min 60 detik). `validate()` menolak nilai di luar batas.
  - `risk_limits_for_paper(settings)`: batas sama persis dengan `core/interfaces/demo.py` (spread 1%, slippage 1%).
  - `build_forward_paper(container, settings)`: menolak `live_trading`, `broadcast_enabled`, `paper_trading=false`, atau `dry_run=false`. Halt diteruskan ke `PaperTradingUseCase`. Spread dihubungkan ke `spread_lookup=None`, sehingga setiap order ditolak `SPREAD_UNAVAILABLE` (fail closed).
  - `run_forward_paper(...)`: loop `Monitor.run_cycle()` -> ambil sinyal ACCEPTED yang dibuat dalam batas usia dan belum pernah dicoba di proses ini -> `ForwardPaperSession.run_once` -> cetak JSON per siklus -> sleep. Jika halt aktif, loop berhenti dan mencetak status HALTED.
- `core/interfaces/cli.py`: subcommand `forward-paper` dengan argumen di atas, validasi awal, halt check (ditambahkan ke daftar perintah yang diblokir saat halt), dan blok dispatch.
- `tests/unit/test_forward_runner.py` (baru, 7 tes): live/broadcast ditolak; validasi argumen; halt memblokir scan dan order; tanpa sumber spread tidak ada order dibuka dan ledger ditulis; sesi bisa dilanjutkan dengan konfigurasi sama; konfigurasi beku berbeda ditolak; `build_forward_paper` menolak non-paper.

## Hasil
- `scripts/run_tests.py`: 999 lulus, 0 gagal, 0 error (sebelumnya 992 + 7 tes baru).
- `compileall`: bersih. Pemeriksaan import tak terpakai pada file baru dan file yang diubah: bersih.

## Tidak berubah
- Aturan RT-06 dan aturan keamanan di AI_RULES.yaml, RULES.md, SECURITY.md.
- Live tetap terkunci (`LIVE_TRADING`, `BROADCAST_ENABLED` ditolak di `core/config.py`).
- Bobot strategi, RSI period, threshold: tidak disentuh.

## Batasan yang masih ada
- Belum ada sumber spread produksi. Akibatnya runner tidak pernah membuka order. Ini disengaja. Hasil forward belum berisi trade sampai sumber spread nyata disambungkan.
- Tes membuat beberapa container `:memory:` tanpa menutupnya. Muncul `ResourceWarning` di log, tidak memengaruhi hasil.
- Idempotensi sinyal diuji lewat set `attempted` dalam satu proses dan kunci `open:{signal.id}` di paper use case. Tes end-to-end dengan sinyal ACCEPTED nyata belum ada.
