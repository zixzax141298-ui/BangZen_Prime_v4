# Instalasi di Termux (Android)

Inti aplikasi hanya memakai pustaka standar Python, sehingga tidak perlu kompilasi Rust
atau paket native. Fallback Python untuk modul Rust dipakai secara otomatis.

## 1. Siapkan Termux

    pkg update && pkg upgrade -y
    pkg install -y python git unzip

Python yang disediakan Termux harus 3.11 atau lebih baru (`python3 --version`).

## 2. Pasang paket inti

    cd ~
    unzip BangZenPrime-v3-main.zip
    cd BangZenPrime-v3-main
    pip install .

## 3. Konfigurasi

    cp .env.example .env

CLI membaca file `.env` di folder kerja. Variabel environment yang sudah di-set
tetap lebih diutamakan daripada isi `.env`. Kunci pengaman (`BANGZEN_LIVE_TRADING`,
`BANGZEN_BROADCAST_ENABLED`, dan lainnya) tetap dikunci dan divalidasi di kode.

## 4. Jalankan

    bangzen-prime status
    bangzen-prime demo --scans 25
    bangzen-prime health

## 5. Dashboard (opsional)

Dashboard memakai paket tambahan:

    pip install ".[dashboard]"
    bangzen-prime dashboard

Jika paket ini belum terpasang, perintah akan menampilkan pesan berisi perintah instalasinya.

## Catatan

- Perintah `scan` dan `discover` memerlukan jaringan. Kunci provider diisi di `.env` bila dibutuhkan (lihat README).
- Tidak ada perintah live trading. Mode live dan broadcast tetap ditolak oleh konfigurasi.

## Monitor terus-menerus (paper only)

Buat file watchlist (satu mint per baris), lalu jalankan:

    cp configs/watchlist.example.txt watchlist.txt
    bangzen-prime monitor --watchlist watchlist.txt --interval-seconds 60 --scans-per-minute 20

Setiap siklus memindai setiap mint sekali, dibatasi anggaran per menit, mencatat perpindahan
fase, lalu mengirim sinyal paper yang diterima ke Telegram lewat outbox. Hentikan dengan Ctrl+C.
Untuk satu siklus saja, tambahkan `--cycles 1`.

Anggaran dihitung per pemindaian token, bukan per panggilan HTTP di tiap adaptor.
Entri paper hanya terjadi kalau AI aktif dan semua bukti fase terpenuhi. Tanpa AI, bot memantau
tetapi tidak membuka posisi paper.

## Profil ringan Termux (BELUM DIVERIFIKASI di perangkat)

Untuk ponsel dengan sumber daya terbatas, pakai profil `termux_light` yang sudah disediakan:

    scripts/run_monitor_profile.sh termux_light

Profil ini memakai interval 300 detik, 5 pemindaian per menit, dan maksimal 25 mint di watchlist.
Nilai ini pilihan awal dan belum diuji pada perangkat nyata. Untuk profil default VPS, gunakan
`vps_default` (60 detik, 20 pemindaian per menit, maksimal 100 mint). Skrip menolak watchlist
yang melebihi batas profil dan tidak menjalankan apa pun jika `bangzen-prime` tidak ada di PATH.

Termux tidak memakai systemd. Menjaga proses tetap hidup (misalnya lewat `tmux` atau
`termux-wake-lock`) adalah tanggung jawab owner dan belum diuji di perangkat.

## Penemuan koin terus-menerus (BELUM DIVERIFIKASI di perangkat)

Perintah `discover` mencari kandidat token baru dari DexScreener, lalu memindainya.
Loop ini berjalan terus sampai dihentikan. Hasilnya hanya sinyal dan catatan paper. Tidak ada order live.

    scripts/run_discover_profile.sh termux_light

Profil `termux_light` memakai jeda 600 detik dan 10 kandidat per siklus. Profil `vps_default`
memakai 60 detik dan 30 kandidat. Penemuan membutuhkan jaringan. Di Termux, pastikan proses
tetap hidup dengan tmux atau termux-wake-lock. Itu belum diuji.
