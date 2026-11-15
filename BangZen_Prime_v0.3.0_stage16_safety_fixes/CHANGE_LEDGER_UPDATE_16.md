# CHANGE LEDGER UPDATE 16 — Perbaikan keselamatan 1 sampai 4

## 1. Kill switch dan .env tidak lagi bergantung pada folder kerja
- Masalah: `HALT.flag` dan `.env` dibaca relatif terhadap folder kerja. Dari folder lain, kill switch tidak terlihat dan `.env` diabaikan tanpa peringatan.
- Perbaikan:
  - `Settings.halt_flag_path` (kunci `BANGZEN_HALT_FLAG_PATH`). Default adalah path absolut `HALT.flag` di folder awal. Path relatif ditolak saat konstruksi.
  - `Settings.halt_active()` menjadi satu-satunya pemeriksaan kill switch. Semua pemanggil memakai method ini.
  - `risk/emergency_stop.py`: default `HALT_FLAG_PATH` sekarang absolut sejak modul diimpor.
  - `BANGZEN_ENV_FILE`: jika diisi dan file tidak ada, startup gagal. Jika `.env` default tidak ada, CLI mencetak peringatan.
  - Ketiga unit systemd menetapkan `BANGZEN_ENV_FILE` dan `BANGZEN_HALT_FLAG_PATH` dalam path absolut.

## 2. Discovery berhenti saat emergency stop aktif di tengah jalan
- Masalah: `discover` hanya memeriksa kill switch sekali saat startup. Pencarian dan scan terus berjalan.
- Perbaikan: `ContinuousDiscoveryUseCase` menerima `halt_check`. Pemeriksaan dilakukan di awal `execute`, dan sebelum setiap pemanggilan scanner. Jika aktif, `HaltEngagedError` dilempar. Loop `discover` di CLI menangkapnya lalu berhenti.
- Batasan granularitas: pemeriksaan dilakukan per batch scan, bukan per token. Satu batch tetap selesai sebelum berhenti.

## 3. Rahasia tidak bocor lewat jalur error
- Temuan lewat tes: pola token Telegram memakai `\b` di awal, sehingga token di dalam URL `/bot<token>/` TIDAK tersaring. Ini celah nyata. Diperbaiki dengan lookaround.
- Redaksi ditambah untuk header `Bearer` dan `x-api-key`.
- Error CLI (`configuration error` dan `error`) sekarang melewati `redact`, karena sebelumnya dicetak mentah ke stderr.
- Pemeriksaan kode: pola `api-key=` di URL Helius sudah tertangkap redaksi log. Kunci Helius tetap dibawa di URL karena saya belum memverifikasi dukungan header di provider. Ini dicatat sebagai sisa risiko.

## 4. WalletSigner cocok dengan titik panggilan
- Masalah: `controlled_execution` memanggil `self._signer.sign(plan)`, tetapi `WalletSigner` hanya punya `sign_transaction`.
- Perbaikan: `WalletSigner.sign(plan)` ditambahkan dan selalu melempar `SigningDisabled`. Jalur itu sekarang gagal tertutup sebagai `REJECTED`, bukan `AttributeError`.
- Batasan: integrasi penuh `ControlledExecution` dengan signer ini belum diuji secara end-to-end. Tes memverifikasi kontrak method dan perilaku penolakan.

## Hasil
- `tests/unit/test_safety_fixes.py`: 20 tes lulus. Mencakup halt path dari folder lain, kegagalan tertutup, discovery berhenti sebelum scan, redaksi token dan header, dan `WalletSigner.sign`.
- Seluruh `tests/unit`: 820 tes, 8 error. Error identik dengan baseline dan semuanya karena `httpx` tidak terpasang. Tidak ada regresi.
- `compileall` bersih. Impor yang tidak terpakai (`halt_engaged` di tiga modul) sudah dihapus.

## BELUM DIVERIFIKASI
- Tes `test_cli_refuses_signal_producing_commands_when_kill_switch_is_on` dan tes e2e tidak bisa dijalankan karena `httpx`. Perilakunya diharapkan tetap sama, tetapi wajib dijalankan ulang.
- Perilaku di VPS nyata: unit systemd dengan `Environment=` baru belum diuji dengan `systemd-analyze verify` pada bentuk yang sudah dirender (dilakukan di tahap berikutnya).
- Integrasi penuh signer dengan `ControlledExecution` di jalur live (jalur ini tetap tidak bisa dicapai).

## Tidak berubah
- AI_RULES.yaml, RULES.md, SECURITY.md, RT-06, live lock, dan readiness gate.
- Tidak ada signing, private key, atau broadcast baru.

## Sisa risiko
- Kunci Helius masih di URL. Perlu verifikasi dukungan header di Helius sebelum diubah.
- `smart_money_adapter.py` mencatat `{e}` pada blok `Funder graph error`. Belum dipastikan apakah pesan exception-nya memuat URL. Redaksi log sekarang menangkap pola kunci, tetapi ini perlu dicek.
