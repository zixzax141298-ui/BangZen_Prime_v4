# BangZen Prime

BangZen Prime adalah bot riset untuk token Solana. Bot memindai kandidat token baru, menilai keamanan
dan likuiditas, menghitung skor heuristik, lalu mengirim **sinyal** dan mencatat **posisi paper**.

> **Status saat ini: PAPER DAN SINYAL SAJA. LIVE TRADING TERKUNCI.**
> Tidak ada izin live. Gate kesiapan live belum lulus (lihat `docs/OWNER_LIVE_READINESS_CHECKLIST.md`).
> Izin live hanya bisa datang dari owner secara tertulis.

Versi: 0.3.0 (stage 16). Bahasa dokumentasi proyek: Indonesia dan Inggris.

---

## Daftar isi

1. Apa yang dilakukan bot dan apa yang tidak
2. Persyaratan
3. Instalasi di Termux
4. Instalasi di VPS / Linux
5. Library dan dependensi
6. Konfigurasi `.env` (lengkap)
7. BYOK: membawa kunci sendiri
8. Perintah CLI dan fitur
9. Strategi yang sekarang
10. Fitur per platform: Termux vs VPS
11. Menjalankan monitor, discovery, dan laporan harian
12. Validasi dan tes
13. Keamanan dan batas eksekusi
14. Keterbatasan dan yang belum terverifikasi
15. Dokumen lain

---

## 1. Apa yang dilakukan bot dan apa yang tidak

**Dilakukan:**
- Menemukan kandidat token baru dari DexScreener (`discover`).
- Memindai token: data pasar, keamanan, pemegang, likuiditas, volume, dan konteks on-chain bila kunci tersedia.
- Menentukan fase lifecycle token. Jika tidak ada data fase, fasenya **UNKNOWN**. Fase tidak ditebak dari waktu.
- Menghasilkan sinyal `ACCEPTED` atau `REJECTED` beserta alasannya.
- Mengirim sinyal ke Telegram (hanya keluar, tidak ada perintah masuk).
- Mencatat posisi **paper** dengan ledger berantai hash dan batas risiko.
- Membuat laporan harian paper.

**Tidak dilakukan (dan tidak akan dilakukan tanpa izin tertulis owner):**
- Tidak membuka order live. `LIVE_TRADING` dan `BROADCAST_ENABLED` ditolak oleh kode.
- Tidak menyimpan private key atau seed phrase. Tidak ada signing dan tidak ada broadcast transaksi.
- Tidak mengklaim profit, win rate, atau keunggulan kompetitif. Skor adalah peringkat heuristik, bukan probabilitas.

---

## 2. Persyaratan

- Python **3.11 atau lebih baru** (proyek menargetkan 3.13).
- Git.
- Akses internet untuk instalasi dan untuk provider data (DexScreener, RugCheck, dan lainnya).
- Opsional: Rust/Cargo untuk validasi native. Tanpa Rust, bot memakai fallback Python.
- Opsional: Docker dan kunci model AI, hanya untuk pemindaian keamanan Strix di VPS.

---

## 3. Instalasi di Termux

Termux cocok untuk menjalankan bot paper dengan profil ringan. Inti aplikasi hanya memakai pustaka standar
Python ditambah dua paket kecil, sehingga tidak perlu kompilasi Rust.

```bash
pkg update && pkg upgrade -y
pkg install -y python git unzip

git clone https://github.com/<repo-anda>/BangZenPrime.git   # atau unzip berkas zip
cd BangZenPrime
python3 -m venv ~/bz-venv
source ~/bz-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .

cp .env.example .env          # lalu isi kunci yang Anda perlukan (lihat bagian 6 dan 7)
bangzen-prime status          # cek mode dan kunci pengaman
bangzen-prime migrate         # buat database
```

Atau gunakan skrip yang sudah disediakan: `scripts/termux_install.sh` (harus dijalankan dengan venv aktif).

Menjalankan dengan profil ringan:

```bash
cp configs/watchlist.example.txt watchlist.txt
scripts/run_monitor_profile.sh termux_light     # pemantauan watchlist
scripts/run_discover_profile.sh termux_light    # penemuan koin
```

Catatan Termux: Android bisa menghentikan proses di latar belakang. Gunakan `tmux` atau `termux-wake-lock`.
Perilaku ini **belum diverifikasi di perangkat**.

---

## 4. Instalasi di VPS / Linux

Tanpa Docker dan tanpa paket native. Jalankan sebagai user biasa, bukan root.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

git clone https://github.com/<repo-anda>/BangZenPrime.git
cd BangZenPrime
cp .env.example .env          # isi kunci sesuai kebutuhan
scripts/install_vps.sh        # buat venv (~/bz-venv), pasang paket, cek versi 0.3.0,
                              # dan render unit systemd ke deploy/generated/
```

`install_vps.sh` menolak jalan sebagai root, menolak jika `.env` mengaktifkan live atau broadcast, dan
**tidak** memakai sudo serta **tidak** mengaktifkan service. Anda memasang unit sendiri:

```bash
# Monitor watchlist (terus-menerus)
sudo cp deploy/generated/bangzen-prime-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bangzen-prime-monitor

# Penemuan koin (terus-menerus)
sudo cp deploy/generated/bangzen-prime-discover.service /etc/systemd/system/
sudo systemctl enable --now bangzen-prime-discover

# Laporan harian (00:10 UTC setiap hari)
sudo cp deploy/generated/bangzen-prime-daily-report.service deploy/generated/bangzen-prime-daily-report.timer /etc/systemd/system/
sudo systemctl enable --now bangzen-prime-daily-report.timer
```

Pantau log: `journalctl -u bangzen-prime-monitor -f`.

Validasi native (opsional, untuk pemeriksaan penuh):

```bash
python3 tools/ci.py --profile vps
```

---

## 5. Library dan dependensi

### Dependensi inti (wajib)
| Paket | Fungsi |
|---|---|
| `httpx>=0.27` | Klien HTTP untuk provider. Dibutuhkan oleh composition root. |
| `defusedxml>=0.7` | Parsing XML yang aman (feed berita dan sumber XML). |

Pustaka standar Python dipakai untuk sisanya: `sqlite3`, `unittest`, `urllib`, `decimal`, dan lainnya.

### Extras opsional (`pip install ".[nama]"`)
| Extra | Paket | Untuk apa |
|---|---|---|
| `dashboard` | `rich`, `python-dotenv`, `pyfiglet` | Dashboard terminal (`bangzen-prime dashboard`) |
| `intel` | `httpx`, `defusedxml` | Adaptor intelijen (berita, sumber tambahan) |
| `ws` | `websockets>=12` | Koneksi WebSocket ke sumber streaming |
| `wallet` | `base58`, `solders` | Pemrosesan alamat wallet. **Tidak untuk signing.** Live tetap terkunci. |
| `dev` | `pytest`, `pytest-asyncio`, `coverage`, `ruff`, `black`, `mypy` | Pengembangan dan linting |
| `security` | `bandit`, `semgrep`, `pip-audit` | Pemindaian keamanan (VPS dan CI) |
| `safety` | `safety>=3.0` | Pemindai dependensi tambahan. Tidak wajib untuk gate inti. |

Contoh: `python -m pip install ".[dashboard]"`.

### Native (opsional)
`native/rust/` berisi modul Rust opsional. Jika Cargo tidak ada, bot memakai implementasi Python.

---

## 6. Konfigurasi `.env` (lengkap)

Salin `.env.example` ke `.env`. File ini sudah di `.gitignore`. Setiap kunci wajib diawali `BANGZEN_`.
Kunci yang tidak dikenal akan **ditolak saat startup** (fail-closed). Variabel environment yang sudah di-set
di shell lebih diutamakan daripada isi `.env`.

### 6.1 Kunci pengaman (jangan diubah ke `true`)
| Variabel | Default | Keterangan |
|---|---|---|
| `BANGZEN_LIVE_TRADING` | `false` | Ditolak jika `true`. Live terkunci. |
| `BANGZEN_BROADCAST_ENABLED` | `false` | Ditolak jika `true`. Tidak ada broadcast. |
| `BANGZEN_PAPER_TRADING` | `true` | Mode paper. |
| `BANGZEN_DRY_RUN` | `true` | Simulasi. |
| `BANGZEN_EMERGENCY_STOP` | `false` | `true` menghentikan semua perintah pemindaian dan eksekusi. Sama dengan file `HALT.flag`. |
| `BANGZEN_HALT_FLAG_PATH` | `<folder awal>/HALT.flag` | Path absolut file kill switch. Relatif ditolak. Dipin di unit systemd agar folder kerja tidak menyembunyikannya. |
| `BANGZEN_ENV_FILE` | `.env` | Lokasi file `.env`. Jika diisi dan file tidak ada, startup gagal. Jika `.env` default tidak ada, CLI memberi peringatan dan hanya memakai environment. |
| `BANGZEN_MODE` | `paper` | Mode operasi. |
| `BANGZEN_OPERATING_MODE` | `TELEGRAM_ONLY` | `TELEGRAM_ONLY` (hanya sinyal), `EXECUTION_ONLY` (paper tanpa Telegram), `HYBRID` (paper dan Telegram). |

### 6.2 Runtime dan database
| Variabel | Default | Keterangan |
|---|---|---|
| `BANGZEN_DB_PATH` | `bangzen.db` | Lokasi SQLite. |
| `BANGZEN_LOG_LEVEL` | `INFO` | Tingkat log. |
| `BANGZEN_WATCHDOG_TIMEOUT_SECONDS` | `5` | Batas watchdog. |
| `BANGZEN_HTTP_TIMEOUT_SECONDS` | `10` | Timeout setiap panggilan HTTP. |
| `BANGZEN_HTTP_MAX_ATTEMPTS` | `3` | Percobaan ulang HTTP. |
| `BANGZEN_MARKET_DATA_MAX_AGE_SECONDS` | `120` | Data pasar lebih tua dari ini dianggap basi. |
| `BANGZEN_POLICY_PATH` | kosong | Path JSON kebijakan lifecycle. Kosong = bawaan. |

### 6.3 Sumber data (opsional, kosong = adaptor mati)
| Variabel | Default | Keterangan |
|---|---|---|
| `BANGZEN_DEXSCREENER_BASE_URL` | `https://api.dexscreener.com` | Sumber penemuan dan data pasar. Tidak perlu kunci. |
| `BANGZEN_RUGCHECK_BASE_URL` | `https://api.rugcheck.xyz/v1` | Pemeriksaan keamanan token. |
| `BANGZEN_HELIUS_API_KEY` | kosong | RPC, riwayat, dan bukti Token-2022. Disarankan untuk pemindaian on-chain. |
| `BANGZEN_GRPC_ENDPOINT` | kosong | Endpoint gRPC bergaya Yellowstone. Harus `https://` jika diisi. |
| `BANGZEN_BIRDEYE_API_KEY` | kosong | Data pasar tambahan. |
| `BANGZEN_SOLANA_TRACKER_API_KEY` | kosong | Data tambahan. |
| `BANGZEN_LUNARCRUSH_API_KEY` | kosong | Data sosial dan sentimen. |
| `BANGZEN_JUPITER_API_KEY` | kosong | Data harga dan rute Jupiter. |
| `BANGZEN_JUPITER_SLIPPAGE_BPS` | `50` | Slippage dalam basis point. |
| `BANGZEN_JITO_TIP_CAP_LAMPORTS` | `100000` | Batas tip Jito. Tidak dipakai untuk eksekusi live. |

### 6.4 Telegram
| Variabel | Default | Keterangan |
|---|---|---|
| `BANGZEN_TELEGRAM_BOT_TOKEN` | kosong | Token bot dari BotFather. Harus diisi bersama chat ID. |
| `BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS` | kosong | Daftar chat ID numerik, dipisah koma. Tanpa duplikat. |

Kedua variabel harus diisi bersama. Jika hanya satu yang diisi, startup gagal.

### 6.5 AI (opsional, ANALIS SAJA)
| Variabel | Default | Keterangan |
|---|---|---|
| `BANGZEN_AI_ENABLED` | `false` | Jika `false`, tidak ada pemanggilan AI. |
| `BANGZEN_AI_PROVIDER_ORDER` | `anthropic` | Daftar provider berurutan, dipisah koma, misalnya `anthropic,openai,grok`. Hanya satu provider aktif per panggilan. Provider berikutnya dipakai jika yang aktif kehabisan kunci atau kuota. Entri pertama menjadi `BANGZEN_AI_PROVIDER`. |
| `BANGZEN_AI_PROVIDER` | `anthropic` | Provider utama (entri pertama dari daftar di atas). |
| `BANGZEN_AI_MODEL` | kosong | Model untuk provider utama saja. Provider cadangan memakai model bawaannya sendiri. |
| `BANGZEN_AI_CONFIDENCE_THRESHOLD` | `0.6` | Tidak lagi dipakai untuk gerbang keputusan. Dipertahankan agar konfigurasi lama tetap valid. |
| `BANGZEN_ANTHROPIC_API_KEY` | kosong | Kunci provider Anthropic. |
| `BANGZEN_OPENAI_API_KEY` | kosong | Kunci provider OpenAI. |
| `BANGZEN_GROK_API_KEY` | kosong | Kunci provider Grok. |

Aturan AI di proyek ini:
- AI **tidak** menyentuh pencarian koin (discovery), scan, atau keputusan beli dan jual.
- AI tidak bisa mengembalikan `BUY`, `SELL`, `HOLD`, atau `SKIP`. Keluaran yang valid hanya berupa analisis:
  `risk_level` (LOW, MEDIUM, HIGH, UNKNOWN), `summary`, `flags` (kode dari daftar tetap), dan `confidence`.
  Kunci apa pun di luar itu, termasuk kunci yang mirip keputusan, membuat keluaran ditolak.
- AI tidak menentukan ukuran posisi, stop loss, take profit, atau slippage.
- Jika semua provider gagal, hasilnya `NO_ANALYSIS`. Status itu tidak punya arti trading.
- Pemicu AI setelah beli atau jual paper **belum dipasang**. Lihat catatan di bagian 14.

### 6.6 Paper, risiko, dan biaya
| Variabel | Default | Keterangan |
|---|---|---|
| `BANGZEN_STARTING_EQUITY` | `1000` | Modal awal paper (dalam quote). |
| `BANGZEN_MAX_RISK_PER_TRADE_PCT` | `1` | Risiko maksimum per posisi, persen. |
| `BANGZEN_MAX_OPEN_POSITIONS` | `3` | Jumlah posisi paper terbuka maksimum. |
| `BANGZEN_MAX_EXPOSURE_QUOTE` | `500` | Eksposur total maksimum. |
| `BANGZEN_MAX_DRAWDOWN_PCT` | `20` | Drawdown yang menghentikan paper. |
| `BANGZEN_FEE_RATE` | `0.001` | Biaya per sisi (0,1%). |
| `BANGZEN_SLIPPAGE_RATE` | `0.005` | Slippage (0,5%). |
| `BANGZEN_MIN_LIQUIDITY_USD` | `10000` | Likuiditas minimum dalam USD. |
| `BANGZEN_MAX_RISK_SCORE` | `60` | Skor risiko maksimum yang masih diterima. |

### 6.7 Yang tidak boleh ada di `.env`
- Variabel private key owner: startup dihentikan dengan pesan FATAL jika `OWNER_PRIVATE_KEY` terdeteksi di environment. **Catatan:** penjaga di `core/config.py` memeriksa nama `OWNER_PRIVATE_KEY` tanpa prefix, sedangkan `.env.example` menulis `BANGZEN_OWNER_PRIVATE_KEY` sebagai contoh yang dilarang. Ketidakcocokan ini dicatat sebagai temuan yang perlu diperiksa (lihat bagian 14). Jangan pernah menaruh private key di mana pun.
- `BANGZEN_BURNER_PRIVATE_KEY`: sudah dihapus (P6).
- `BANGZEN_WALLET_PUBLIC_ADDRESS` hanya boleh berisi alamat publik. Alamat publik bukan private key, tetapi
  mengungkap aktivitas on-chain.
- Nama tanpa prefix (`TELEGRAM_TOKEN`, `CABAL_HUNTER_*`) tidak dibaca. Gunakan nama `BANGZEN_*`.

---

## 7. BYOK: membawa kunci sendiri

BYOK (Bring Your Own Key) berarti Anda menyediakan kunci provider sendiri. Proyek ini tidak menyediakan
kunci bersama, dan tidak menyimpan kunci di repositori.

### Kunci dan fungsinya
| Kunci | Wajib? | Dipakai untuk |
|---|---|---|
| `BANGZEN_TELEGRAM_BOT_TOKEN` + `BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS` | Untuk notifikasi | Mengirim sinyal dan laporan harian |
| `BANGZEN_HELIUS_API_KEY` | Disarankan | Pemindaian on-chain, riwayat, bukti Token-2022 |
| `BANGZEN_ANTHROPIC_API_KEY` / `OPENAI` / `GROK` | Hanya jika AI dipakai | Saran AI (penasihat) |
| `BANGZEN_BIRDEYE_API_KEY`, `SOLANA_TRACKER`, `LUNARCRUSH`, `JUPITER` | Opsional | Data tambahan |

DexScreener dan RugCheck dipakai lewat URL dasar di konfigurasi dan tidak memerlukan kunci di konfigurasi ini.

### Aturan BYOK
1. Jangan pernah commit `.env`.
2. Jangan pernah memasukkan API key, seed phrase, atau private key ke kode, tes, log, Telegram, atau prompt AI.
3. Gunakan kredensial terpisah dan berhak akses minimum untuk pengembangan dan produksi.
4. Kunci hanya diberikan ke adaptor yang memerlukannya.
5. Simpan kredensial CI di GitHub Actions Secrets.
6. Rotasi kunci jika pernah terekspos.

### Cara mendapatkan dan memasang
1. Buat akun di provider yang Anda pilih, lalu buat kunci.
2. Tambahkan kunci ke `.env` (`BANGZEN_NAMA_KUNCI=nilai`).
3. Cek dengan `bangzen-prime status`. Perintah ini menampilkan pengaturan efektif tanpa rahasia. Verifikasi bahwa kunci tidak tercetak di terminal atau log sebelum berbagi keluarannya.
4. Jika kunci bocor, hapus di dashboard provider, buat yang baru, lalu ubah `.env`.

Telegram: buat bot lewat @BotFather, lalu ambil chat ID Anda. Bot hanya mengirim ke chat ID yang ada di allowlist.

---

## 8. Perintah CLI dan fitur

Semua perintah dijalankan dengan `bangzen-prime <perintah>`.

| Perintah | Fungsi | Jaringan |
|---|---|---|
| `status` | Tampilkan pengaturan efektif dan kunci pengaman (tanpa rahasia) | Tidak |
| `migrate` | Terapkan migrasi database (idempoten) | Tidak |
| `demo --scans N` | Simulasi offline dengan data palsu berlabel. Hanya demo, bukan bukti performa. | Tidak |
| `scan --chain solana --mints ...` | Pindai satu atau beberapa mint | Ya |
| `discover --interval-seconds 60 --limit 30` | Penemuan koin terus-menerus. `--once` untuk satu siklus. | Ya |
| `monitor --watchlist watchlist.txt --interval-seconds 60 --scans-per-minute 20` | Pantau watchlist terus-menerus (paper). `--cycles N` untuk berhenti setelah N siklus. | Ya |
| `forward-paper ...` | Sesi forward paper dengan ledger berantai hash | Ya |
| `outbox` | Satu putaran pengiriman outbox | Ya (Telegram) |
| `daily-report [--day YYYY-MM-DD] [--send]` | Cetak laporan harian UTC. `--send` mengirim ke Telegram. | Hanya dengan `--send` |
| `dashboard` | Dashboard terminal (butuh extra `dashboard`) | Ya |
| `health` | Cek kesehatan sistem. Keluar dengan kode 1 jika tidak OK. | Tidak |
| `audit-verify` | Verifikasi rantai hash audit log | Tidak |
| `soak --cycles N` | Uji ketahanan dengan data sintetis | Tidak |
| `backup PATH` / `restore PATH` | Cadangan dan pemulihan database | Tidak |
| `prune --days N` | Hapus data lama sesuai retensi | Tidak |

Perintah `scan`, `discover`, `outbox`, `monitor`, dan `forward-paper` **ditolak** jika emergency stop aktif.

### Fitur utama
- **Ledger paper** berantai hash: setiap entri terhubung ke entri sebelumnya, sehingga perubahan bisa dideteksi.
- **Batas kerugian harian** yang dicek sebelum order paper dibuka.
- **Fase lifecycle** tersimpan di database (migrasi 0004 dan 0006).
- **Outbox at-least-once** untuk sinyal, dengan dead-letter setelah percobaan maksimum.
- **Laporan harian** dengan pengiriman yang tidak mengirim ulang potongan yang sudah terkirim (lihat `docs/DAILY_REPORT.md`).
- **Batas memori, rotasi log, cooldown discovery tersimpan**, dan supervisor dengan backoff.
- **Demo** memakai `SIMULATED_SPREAD_PCT` sebagai asumsi offline yang diberi label. Ini hanya untuk demo.

---

## 9. Strategi yang sekarang

Bot memakai alur keputusan bertingkat. Setiap langkah bisa menolak kandidat, dan alasan penolakan disimpan.

1. **Penemuan.** DexScreener memberi kandidat baru. Kandidat yang baru dipindai tidak dipindai ulang selama
   cooldown 1800 detik. Kandidat yang sementara gagal dicoba lagi setelah 60 detik.
2. **Data pasar.** Harga dan riwayat dikumpulkan. Riwayat minimum **15 titik**. RSI memakai periode **14**.
3. **Keamanan.** Pemeriksaan keamanan, pemegang, honeypot, dan sybil dijalankan. Bukti yang hilang, basi,
   parsial, atau bertentangan **tidak dianggap aman**.
4. **Fase lifecycle.** Fase diambil dari `token_lifecycle`. Jika tidak ada baris, fasenya **UNKNOWN**.
   Kebijakan per fase (`configs/phase_policy.json`):

   | Fase | Mode | Bukti wajib |
   |---|---|---|
   | UNKNOWN, LAUNCH | WATCH (hanya pantau) | safety, holders |
   | EARLY | ENTER_PAPER | safety, holders, liquidity, intel |
   | GROWTH, MATURE | ENTER_PAPER | safety, holders, liquidity, volume, intel |
   | CEX_LISTED | WATCH | safety, holders |

5. **Skor heuristik.** Skor 0 sampai 100 dari empat komponen:
   - Mode umum: likuiditas 35%, volume 20%, keamanan 30%, momentum 15%.
   - Fase awal (UNKNOWN, LAUNCH, EARLY): likuiditas 15%, volume 30%, keamanan 35%, momentum 20%.
   - Likuiditas penuh pada 100.000 USD. Volume penuh pada 500.000 USD. Momentum berpusat pada RSI 55.
   - Skor minimum untuk diterima: **45**.
6. **Filter likuiditas dan volume.** Likuiditas minimum dari `BANGZEN_MIN_LIQUIDITY_USD` (kecuali fase tertentu
   yang dikecualikan). Volume 24 jam minimum **5.000 USD**.
7. **Level harga.** Stop dan target dihitung dari volatilitas, dibatasi antara 0,25% dan 12%, dengan
   pengali stop 2 dan target 3. Rasio risk/reward minimum **1,5**.
8. **Keputusan.** Sinyal `ACCEPTED` hanya jika tidak ada alasan penolakan dan level valid.
9. **AI (opsional, analis saja).** AI hanya menghasilkan analisis risiko. AI tidak punya wewenang di pencarian,
   scan, atau keputusan beli dan jual. Veto keamanan deterministik tetap final.
10. **Eksekusi paper.** Batas paper: spread 1%, slippage 1%. Order paper dibuka hanya jika semua langkah di atas lulus.
11. **Notifikasi.** Sinyal diterima masuk outbox lalu dikirim ke Telegram.

### Yang perlu dipahami dengan jujur
- **Skor adalah peringkat heuristik, bukan probabilitas atau ekspektasi profit.** Keyakinan (`score / 100`)
  belum dikalibrasi secara statistik.
- **Bobot dan ambang belum tervalidasi.** Tidak ada bobot atau threshold yang diklaim optimal. Perubahan
  hanya boleh dilakukan dengan bukti walk-forward out-of-sample.
- **Belum ada sumber spread produksi.** Akibatnya setiap order paper ditolak dengan `SPREAD_UNAVAILABLE`
  (fail-closed). Artinya ledger forward belum terisi dengan trade. Ini disengaja.
- **Belum ada dataset historis point-in-time.** Token mati, rug, delisted, dan likuiditas rendah belum
  tercakup dalam data historis yang terverifikasi.
- Modul strategi tersedia di `bangzen_prime/strategies/` (misalnya momentum, mean reversion, sniper, dan
  lainnya). Modul yang aktif dalam alur utama ditentukan oleh dispatcher dan konfigurasi. README ini
  tidak mengklaim semua modul aktif atau sudah tervalidasi.

Rincian riset dan protokol evaluasi: `docs/STRATEGY_RESEARCH.md`.

---

## 10. Fitur per platform: Termux vs VPS

| Fitur | Termux | VPS |
|---|---|---|
| Instalasi inti (`pip install .`) | Ya | Ya |
| `status`, `migrate`, `demo`, `health`, `backup` | Ya | Ya |
| `scan`, `discover`, `monitor`, `forward-paper` | Ya, profil `termux_light` | Ya, profil `vps_default` |
| Telegram dan laporan harian | Ya (dengan jaringan) | Ya |
| Layanan otomatis (systemd) | Tidak. Gunakan tmux atau termux-wake-lock | Ya, `install_vps.sh` merender unit |
| Dashboard | Terbatas (terminal kecil) | Ya |
| Validasi native (Rust, cargo-audit) | Tidak | Ya (`tools/ci.py --profile vps`) |
| Pemindaian Strix (Docker) | Tidak | Ya |
| Pemindaian keamanan (`.[security]`) | Terbatas | Ya |

Profil:

| Profil | Interval monitor | Scan per menit | Maks mint | Interval discover | Limit discover |
|---|---|---|---|---|---|
| `vps_default` | 60 detik | 20 | 100 | 60 detik | 30 |
| `termux_light` | 300 detik | 5 | 25 | 600 detik | 10 |

Angka profil `termux_light` adalah pilihan awal dan **belum diukur** di perangkat.

---

## 11. Menjalankan monitor, discovery, dan laporan harian

### Monitor watchlist (paper)
```bash
cp configs/watchlist.example.txt watchlist.txt     # satu mint per baris
bangzen-prime monitor --watchlist watchlist.txt --interval-seconds 60 --scans-per-minute 20
```
Setiap siklus memindai setiap mint sekali, dibatasi anggaran per menit, mencatat perpindahan fase,
lalu mengirim sinyal ke outbox. Hentikan dengan Ctrl+C.

### Penemuan koin terus-menerus
```bash
bangzen-prime discover --interval-seconds 60 --limit 30
```
Loop berjalan sampai dihentikan. Lihat `docs/CONTINUOUS_DISCOVERY.md`.

### Laporan harian
```bash
bangzen-prime daily-report                 # cetak laporan kemarin (UTC), tanpa jaringan
bangzen-prime daily-report --send          # kirim ke Telegram
```
Laporan memuat jumlah sinyal, order paper, fase, dan outbox gagal. Tidak ada angka profit. Lihat `docs/DAILY_REPORT.md`.

---

## 12. Validasi dan tes

Dari root repositori:

```bash
python scripts/run_tests.py                 # suite lengkap (stdlib unittest)
python -m compileall -q bangzen_prime tests scripts tools
python3 tools/ci.py --profile termux        # cek portabel
python3 tools/ci.py --profile vps           # cek penuh, termasuk Rust bila ada
```

Status CI:
- **PASS**: perintah benar-benar berjalan dan keluar dengan 0.
- **FAIL**: perintah berjalan dan gagal, atau timeout.
- **BLOCKED**: alat atau berkas wajib tidak ada.
- **NOT RUN**: pemeriksaan opsional tidak dijalankan.
- **NOT APPLICABLE**: komponen tidak relevan untuk profil ini.

Alat yang wajib tetapi hilang tidak pernah dianggap PASS.

`scripts/run_tests.py` memeriksa dulu dependensi `httpx` dan `defusedxml`. Jika salah satu hilang, tes tidak
dijalankan dan pesan kesalahan ditampilkan.

Tes yang memerlukan `httpx` tidak bisa dijalankan tanpa paket itu. Tes yang hanya memakai pustaka standar bisa
dijalankan langsung, misalnya `python -m unittest tests/unit/test_daily_report.py`.

Jumlah tes per tahap dicatat di `CHANGE_LEDGER_UPDATE_NN.md`. Angka 999 lulus adalah hasil terakhir
suite penuh yang benar-benar dijalankan (stage 16). Tahap berikutnya menambah tes, tetapi suite penuh
belum dijalankan ulang di lingkungan yang punya `httpx`.

Pengembangan dan keamanan:
```bash
python -m pip install -e ".[dev]"
python -m pip install -e ".[security]"     # VPS/Linux
```

---

## 13. Keamanan dan batas eksekusi

- Data pasar dan on-chain hanya dibaca. Eksekusi hanya paper atau simulasi.
- Tidak ada penyimpanan private key atau seed phrase di repositori.
- Tidak ada signing transaksi live atau broadcast.
- Saran AI bersifat penasihat.
- Veto keamanan dan risiko deterministik memegang keputusan akhir.
- Bukti keamanan yang hilang, basi, parsial, atau bertentangan **tidak** dianggap aman.
- Kill switch (`HALT.flag` atau `BANGZEN_EMERGENCY_STOP`) dicek sebelum setiap siklus discovery, monitor, dan forward, serta sebelum setiap batch scan. Jika status file tidak bisa dibaca, kill switch dianggap aktif.
- Status **HUMAN_REVIEW_CANDIDATE** bukan izin trading.

Baca `AI_RULES.yaml`, `SECURITY.md`, dan `RULES.md` sebelum mengubah kode.

### Strix (pemindaian keamanan AI, opsional)
Strix adalah alat tambahan berbasis AI. Strix **tidak** menggantikan CI deterministik, tes, analisis statis,
atau audit dependensi. Untuk pemindaian lokal, gunakan VPS atau workstation Linux dengan Docker dan kunci
LLM milik Anda sendiri. Ikuti instruksi resmi di https://github.com/usestrix/strix dan https://docs.strix.ai.

```bash
strix -n -t ./ --scan-mode standard --max-budget 10
```

Pindai hanya repositori atau sistem yang Anda miliki atau berwenang uji. Jangan pernah membiarkan scanner
melihat rahasia wallet, kredensial produksi, atau private key. Periksa temuan sebelum menerapkan perubahan.

### GitHub Actions
Workflow menginstal alat pengembangan dan keamanan, lalu menjalankan gate validasi yang sama. Kegagalan
provisioning runner sebelum langkah dijalankan adalah blocker infrastruktur, bukan lulus atau gagal kode.
Kredensial scanner berbayar (misalnya Safety API) **tidak** wajib untuk gate inti.

### Aturan pull request
Setiap PR harus menyebutkan tujuan, commit dasar dan head, berkas yang diubah, perintah validasi beserta hasilnya,
pemeriksaan yang tidak dijalankan, batasan yang diketahui, dampak keamanan, dan Change Ledger.
Jangan pernah menghapus atau melemahkan tes agar gate hijau.

---

## 14. Keterbatasan dan yang belum terverifikasi

**Belum terverifikasi di lingkungan nyata:**
- Pemasangan dan layanan di Termux dan VPS sungguhan.
- Pengiriman Telegram nyata, termasuk rate limit dan respons API.
- Penemuan DexScreener nyata dan batas rate limitnya.
- Perilaku timer dan `Persistent=true` setelah VPS mati.
- Proses yang dihentikan di tengah pengiriman (duplikat at-least-once).
- Dua proses yang berjalan bersamaan.
- Wheel build yang menyertakan migrasi `*.sql` (verifikasi item 5).
- CI lint dan keamanan penuh (masih NOT RUN di lingkungan sandbox tanpa jaringan).
- Python 3.13 (pengujian sebelumnya di 3.12).

**Belum ada (keterbatasan desain):**
- Sumber spread dan harga produksi. Forward ledger belum terisi trade.
- Data historis point-in-time dengan token mati dan rug.
- Validasi out-of-sample untuk bobot dan threshold.
- Kalibrasi keyakinan.
- Dedup untuk notifikasi signal (saat ini at-least-once lewat outbox).
- Perintah masuk Telegram. Telegram hanya keluar.

**Temuan yang perlu diperiksa:**
- Nama variabel owner private key: penjaga memeriksa `OWNER_PRIVATE_KEY`, contoh `.env.example` memakai `BANGZEN_OWNER_PRIVATE_KEY`. Pastikan kedua bentuk dicakup dan diuji.
- Keluaran `status` belum diverifikasi terhadap kemungkinan kebocoran rahasia dengan tes khusus.

**Keterbatasan lain:**
- Pemindai dan tes memakai fixture, bukan data nyata.
- Tes membuat beberapa koneksi `:memory:` tanpa menutupnya. Ini menimbulkan `ResourceWarning`, tidak memengaruhi hasil.

---

## 15. Dokumen lain

| Dokumen | Isi |
|---|---|
| `CHANGE_LEDGER_UPDATE_*.md` | Catatan setiap tahap: perubahan, bukti, dan batasan |
| `docs/OWNER_LIVE_READINESS_CHECKLIST.md` | Gate kesiapan live (status: TIDAK SIAP) |
| `docs/STRATEGY_RESEARCH.md` | Protokol evaluasi dan riset strategi |
| `docs/TERMUX.md` | Panduan Termux |
| `docs/CONTINUOUS_DISCOVERY.md` | Penemuan koin terus-menerus |
| `docs/DAILY_REPORT.md` | Laporan harian dan semantik pengiriman |
| `docs/CONFIGURATION.md` | Konfigurasi rinci |
| `docs/OPERATING_MODES_AND_EXECUTION_LOCK.md` | Mode operasi dan kunci eksekusi |
| `AI_RULES.yaml`, `RULES.md`, `SECURITY.md` | Aturan keamanan (termasuk RT-06, tidak boleh diubah) |
| `AGENTS.md` | Aturan untuk agen pengembang |

---

## Risk notice

Aset digital sangat fluktuatif dan bisa menyebabkan kehilangan total. Backtest, pemindai, model AI, dan
pemeriksaan keamanan **tidak** menjamin profit, eksekusi yang aman, atau perlindungan dari manipulasi pasar.
Proyek ini adalah alat riset dan paper. Keputusan apa pun soal dana sungguhan adalah tanggung jawab owner,
dan hanya boleh diambil setelah gate kesiapan live lulus dan izin tertulis diberikan.
