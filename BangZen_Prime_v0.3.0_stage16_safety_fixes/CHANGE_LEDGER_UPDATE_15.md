# CHANGE LEDGER UPDATE 15 — AI sebagai analis saja, dengan router provider berurutan

## Keputusan owner
- AI tidak boleh menyentuh pencarian koin, scan, atau keputusan beli dan jual.
- AI hanya bertugas sebagai analis. Jika kunci atau kuota satu provider habis, provider berikutnya menggantikan.

## Hasil audit sebelum perubahan
- `AIBrain.decide` masih mengembalikan `BUY` atau `SKIP`, dan itu melanggar `AI_RULES` dan konstitusi.
- `AICommander.execute` hanya dipanggil dari tes. Tidak ada pemanggilan runtime dari discovery, scan,
  atau eksekusi. Jadi AI tidak menyentuh pencarian koin.
- Tes e2e `test_scan_flow` menyetel `scan.ai_brain`, tetapi `ScanMarketUseCase` tidak membacanya.
  Tes itu mengasumsikan AI bisa menerima kandidat, dan asumsi itu sudah tidak sesuai dengan kontrak.

## Ditambahkan
- `bangzen_prime/research/ai_router.py`: `AIRouter`. Mencoba provider berurutan dan hanya satu yang aktif per panggilan.
  Pindah ke provider berikutnya saat error 400, 401, 402, 403, 404, 429, 5xx, circuit-open, atau error jaringan yang bisa
  diulang. Error lain dilempar apa adanya. Jika semua gagal, dilempar `ExternalServiceError` yang bisa diulang tanpa kunci.
- `tests/unit/test_ai_router.py`: 8 tes.
- `BANGZEN_AI_PROVIDER_ORDER` (kunci yang dikenal, parsing, validasi tanpa duplikat, entri pertama = `ai_provider`).

## Diubah
- `research/ai_brain.py`: kontrak analis. Schema keluaran: `risk_level`, `summary`, `flags`, `confidence`. Kunci lain ditolak.
  Gerbang `BUY` dan parameter `threshold` dihapus. `decide` menjadi `analyze`. Status keluaran `ANALYSIS` atau `NO_ANALYSIS`.
  Prompt sistem ditulis ulang sebagai analis yang dilarang memberi keputusan trading.
- `research/ai_commander.py`: tidak ada cabang `BUY`. Hasil analisis dicatat dan dikembalikan. Penolakan prefilter
  mengembalikan `NO_ANALYSIS`.
- `core/config.py`: `ai_provider_order`, validasi, dan syarat `ai_enabled` diubah menjadi "minimal satu provider berkunci".
- `core/bootstrap.py`: membangun router dari daftar provider yang punya kunci. Model kustom hanya untuk provider pertama.
- `tests/unit/test_ai_brain_hardening.py`: ditulis ulang dengan 15 tes kontrak analis. Tes konteks dan keamanan dipertahankan.
- `tests/e2e/test_scan_flow.py`, `tests/integration/test_v3_adapters.py`, `tests/unit/test_ai_commander_sybil_gate.py`,
  `tests/unit/test_sybil_and_commander_safety.py`: diperbarui ke kontrak analis (lihat "BELUM DIVERIFIKASI").
- `README.md`: bagian AI dan status pemicu pasca-trade.

## Hasil
- `tests/unit/test_ai_brain_hardening.py`: 15 lulus.
- `tests/unit/test_ai_router.py`: 8 lulus.
- `tests/unit/test_constitution_v14_2.py`: 7 lulus.
- `tests/unit/test_settings.py`: 32 lulus.
- Seluruh `tests/unit` dijalankan dengan `discover`: 800 tes, 8 error. Baseline zip asli menghasilkan 8 error
  yang sama. Semuanya karena `httpx` tidak terpasang, yaitu `test_ai_commander_sybil_gate`, `test_sybil_and_commander_safety`,
  `test_forward_runner`, `test_signal_gates`, `test_sybil_cache_budget`, dan tiga kasus `test_cli_refuses...`.
  Tidak ada regresi baru.
- `python -m compileall -q bangzen_prime tests`: bersih.

## BELUM DIVERIFIKASI
- Tes e2e dan integrasi yang diperbarui tidak bisa dijalankan karena `httpx`:
  `tests/e2e/test_scan_flow.py`, `tests/integration/test_v3_adapters.py`, `tests/unit/test_ai_commander_sybil_gate.py`,
  `tests/unit/test_sybil_and_commander_safety.py`. Perubahannya mekanis, tetapi wajib dijalankan dengan `httpx`.
- Wiring router di bootstrap (`build_intel_stack`) hanya tervalidasi lewat kompilasi, karena bootstrap butuh `httpx`.
- Failover ke provider nyata (kunci habis, kuota) belum diuji dengan panggilan jaringan sungguhan.

## Belum dikerjakan (langkah berikutnya)
- Pemicu AI setelah beli atau jual paper. Perlu hook pada event order paper dibuka dan ditutup, dengan bukti yang tidak
  memuat PnL atau hasil. Ini butuh persetujuan owner atas bentuk bukti, karena `AI_RULES` melarang AI menerima data hasil.
- `ai_confidence_threshold` sudah tidak dipakai untuk keputusan. Pertimbangkan penghapusan setelah konfigurasi lama dibersihkan.
- Pengecualian `OWNER_PRIVATE_KEY` dari temuan sebelumnya masih terbuka.

## Tidak berubah
- AI_RULES.yaml, RULES.md, SECURITY.md, RT-06, live lock, dan readiness gate.
- Tidak ada signing, private key, atau broadcast.
