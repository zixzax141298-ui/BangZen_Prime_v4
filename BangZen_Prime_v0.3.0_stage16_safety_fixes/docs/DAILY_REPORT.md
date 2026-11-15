# Laporan harian paper dan pengiriman Telegram

## Isi laporan
Laporan untuk satu hari UTC berisi jumlah sinyal (diterima dan ditolak), order paper per status,
jumlah fase posisi paper yang tercatat, dan jumlah outbox yang gagal permanen. Laporan selalu
diberi label `PAPER ONLY`. Laporan tidak memuat PnL, profit, atau angka performa.

## Pemakaian
    bangzen-prime daily-report                       # cetak laporan kemarin (UTC), tanpa jaringan
    bangzen-prime daily-report --day 2026-11-10      # hari UTC tertentu yang sudah selesai
    bangzen-prime daily-report --send                # kirim ke allowlist Telegram

`--send` hanya berjalan jika mode operasi mengizinkan Telegram dan token serta chat ID sudah
diisi di `.env`. Jika salah satu tidak terpenuhi, perintah keluar dengan error dan tidak mengirim apa pun.
Hari yang belum selesai (termasuk hari ini) ditolak.

## Semantik pengiriman: at-least-once, bukan exactly-once
- Laporan dibekukan sekali per hari di tabel `daily_reports`. Pengiriman ulang selalu memakai teks yang sama.
- Isi dipotong per baris ke batas 4000 karakter. Setiap pasangan (potongan, chat) punya dedup key sendiri.
- Key dengan status SENT tidak pernah dikirim ulang.
- Key yang gagal ditandai FAILED dan dicoba lagi pada pemanggilan berikutnya.
- Proses yang berhenti setelah Telegram menerima pesan tetapi sebelum status SENT ditulis akan
  menyebabkan key tertinggal di SENDING. Setelah lease 2 menit habis, key itu bisa dikirim lagi.
  Akibatnya penerima bisa menerima satu potongan dua kali. Ini sengaja tidak dicegah, dan
  exactly-once tidak diklaim.
- Jika satu potongan gagal pada sebuah chat, chat itu berhenti agar urutan potongan terjaga.
  Chat lain tetap menerima potongannya.
- Pesan error yang disimpan hanya berisi teks aman dari adaptor atau teks generik `send failed`.
  Token tidak pernah ditulis ke ledger.

## Batasan
- Jadwal: timer systemd `bangzen-prime-daily-report.timer` berjalan setiap hari pukul 00:10 UTC dan
  mengirim laporan hari UTC sebelumnya. Dipasang oleh `scripts/install_vps.sh`, tidak diaktifkan otomatis.
  `Persistent=true` menjalankan satu kali jika VPS mati saat jadwal. Hari yang terlewat tidak dikejar.
- Jika mode operasi tidak mengizinkan Telegram, timer akan gagal setiap hari dengan pesan di journal.
- Dedup signal notification memakai outbox yang sudah ada (at-least-once, lihat outbox_worker.py).
  Ledger ini belum dipakai untuk signal.
- Perilaku nyata di Telegram belum diuji dengan koneksi sungguhan. Semua tes memakai transport palsu.

## Pemasangan timer (VPS)
    sudo cp deploy/generated/bangzen-prime-daily-report.service deploy/generated/bangzen-prime-daily-report.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now bangzen-prime-daily-report.timer
    systemctl list-timers bangzen-prime-daily-report.timer
