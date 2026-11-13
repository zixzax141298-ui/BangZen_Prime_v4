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

- Perintah `scan`, `discover`, dan `intel` memerlukan jaringan dan API key dari `.env`.
- Tidak ada perintah live trading. Mode live dan broadcast tetap ditolak oleh konfigurasi.

## Monitor terus-menerus (paper only)

Buat file watchlist (satu mint per baris), lalu jalankan:

    cp config/watchlist.example.txt watchlist.txt
    bangzen-prime monitor --watchlist watchlist.txt --interval-seconds 60 --scans-per-minute 20

Setiap siklus memindai setiap mint sekali, dibatasi anggaran per menit, mencatat perpindahan
fase, lalu mengirim sinyal paper yang diterima ke Telegram lewat outbox. Hentikan dengan Ctrl+C.
Untuk satu siklus saja, tambahkan `--cycles 1`.

Anggaran dihitung per pemindaian token, bukan per panggilan HTTP di tiap adaptor.
Entri paper hanya terjadi kalau AI aktif dan semua bukti fase terpenuhi. Tanpa AI, bot memantau
tetapi tidak membuka posisi paper.
