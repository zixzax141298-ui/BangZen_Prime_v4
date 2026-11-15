# Checklist kesiapan live trading (untuk keputusan owner)

**Status saat ini: LIVE TIDAK SIAP. Tidak ada otorisasi live.**

Dokumen ini memetakan syarat live dari `AI_RULES.yaml` (`operating_modes.live.requires`,
`non_negotiable_safety`) dan `SECURITY.md` §7a terhadap bukti yang ada di repo. Ini bukan
persetujuan dan tidak membuka live. Status yang dipakai:

- **DONE**: ada implementasi dan tes yang bisa dicek.
- **PARTIAL**: ada bagian, belum lengkap atau belum tersambung ke jalur utama.
- **MISSING**: belum ada.
- **BLOCKED**: belum bisa diverifikasi tanpa jaringan atau perangkat.

## 1. Syarat dari AI_RULES (`operating_modes.live.requires`)

| # | Syarat | Status | Bukti / catatan |
|---|---|---|---|
| 1 | Otorisasi tertulis owner untuk perubahan spesifik | MISSING | Tidak ada dokumen otorisasi. Permintaan umum tidak dihitung. |
| 2 | Review keamanan independen | MISSING | Belum ada reviewer independen. |
| 3 | Tes risiko dan eksekusi dengan bukti terdokumentasi | PARTIAL | Tes risk engine dan gateway ada. Belum ada tes end-to-end buy/sell lifecycle (`docs/KNOWN_LIMITATIONS.md` baris 113). |
| 4 | Simulasi transaksi dan rekonsiliasi terverifikasi | MISSING | Tidak ada RPC simulasi di mainnet. Rekonsiliasi saldo hanya helper, belum tersambung ke broadcast (baris 22, 71). |
| 5 | Prosedur emergency stop dan rollback yang teruji | PARTIAL | `HALT.flag` terimplementasi dan diuji (`tests/unit/test_halt_flag.py`). Prosedur rollback belum diuji. |
| 6 | PR implementasi live terpisah yang disetujui | MISSING | Belum ada PR. |

## 2. Komponen jalur eksekusi (`docs/KNOWN_LIMITATIONS.md` baris 81–86)

| Komponen | Status | Catatan |
|---|---|---|
| Transaction builder produksi | MISSING | Jupiter adapter hanya quote. |
| Decoder transaksi versi 0 dan inspeksi instruksi, program, akun | MISSING | Adapter menerima versi 0, tapi belum decode untuk memeriksa sebelum signing. |
| Adapter RPC kirim dan konfirmasi | MISSING | Tidak tersambung di bootstrap. |
| Verifikasi wallet dan alamat | MISSING | Disyaratkan oleh docs, belum ada. |
| Signing terintegrasi dalam pipeline penuh | PARTIAL | `WalletSigner` ada. Default-nya dinonaktifkan dan tidak tersambung ke pipeline lengkap. |
| Cek kesegaran quote dan slippage | PARTIAL | Ada di risk engine, belum divalidasi di jalur live. |
| Idempotensi kirim | PARTIAL | Intent disimpan sebagai UNKNOWN sebelum signing (baris 124). Belum diuji di jaringan nyata. |
| Rekonsiliasi signature dan saldo pasca-trade | MISSING | Belum tersambung. |
| Jito bundle dan Jupiter execute tidak boleh dipakai untuk transaksi yang sama | MISSING | Aturan dicatat, belum ada penegakan. |

## 3. Syarat keamanan (`SECURITY.md` §7a dan `non_negotiable_safety`)

| Syarat | Status | Catatan |
|---|---|---|
| `LIVE_TRADING` dan `BROADCAST_ENABLED` ditolak | DONE | `Settings` menolak keduanya. Diuji di `test_v3_core`, `test_settings`, dan `test_readiness_gate` (live lock). |
| AI tidak punya akses secret, signing, broadcast | PARTIAL | Dinyatakan di AI_RULES dan SECURITY.md. Belum diverifikasi ulang di sesi ini. Perlu audit dan review independen. |
| Risk Engine punya veto final | PARTIAL | Ada, tapi belum diuji terhadap jalur live karena jalur live tidak ada. |
| Kill switch tetap aktif setelah restart | DONE | `HALT.flag` dibaca dari file, bukan memori. Fail-closed bila status tidak bisa dibaca. |
| Data yang hilang diperlakukan sebagai UNAVAILABLE | DONE (di modul riset) | `cost_model` dan `readiness_gate`. Belum diterapkan ke jalur live. |
| Secret tidak masuk log atau Telegram | BLOCKED | Perlu audit log dengan data nyata. |

## 4. Syarat riset (gate `HUMAN_REVIEW_CANDIDATE`)

Gate hanya bisa memberi status layak ditinjau manusia. Gate tidak pernah membuka live.

| Syarat | Status |
|---|---|
| Data historis point-in-time dengan token mati dan rug | MISSING |
| Backtest walk-forward dengan baseline | PARTIAL (modul ada, belum ada data) |
| Model biaya dengan data nyata | MISSING (model ada, input belum terukur) |
| Forward paper record dengan konfigurasi beku | PARTIAL (ledger ada, belum ada pembuat trade) |
| Threshold gate disetujui owner | MISSING (usulan saja) |

## 5. Yang harus dilakukan owner sebelum ada pekerjaan live

1. Menyetujui atau mengubah threshold gate secara tertulis.
2. Menentukan sumber data historis dan menyediakan aksesnya.
3. Menentukan apakah ada tahap live kecil yang akan diotorisasi, dan kapan. Tanpa itu, tidak ada pekerjaan live yang dimulai.
4. Menunjuk reviewer keamanan independen.

Sampai semua poin di atas terpenuhi, bot ini hanya boleh dijalankan dalam mode baca saja dan paper.
