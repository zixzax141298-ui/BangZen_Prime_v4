# CHANGE LEDGER UPDATE 14 — README lengkap (dokumentasi, tanpa perubahan perilaku)

## Ditambahkan / diubah
- `README.md`: diganti dengan dokumen lengkap. Mencakup instalasi Termux dan VPS, daftar library
  dan extras, seluruh variabel `.env` dengan default dari `.env.example` dan kode, BYOK, perintah CLI,
  strategi yang berlaku sekarang, perbandingan Termux vs VPS, validasi, keamanan, dan batasan.
  Bagian keamanan, Strix, GitHub Actions, aturan PR, dan risk notice dari README lama dipertahankan.
  README lama disimpan di luar repo sebagai referensi.
- `docs/TERMUX.md`: perintah `intel` dihapus dari catatan karena tidak ada di parser CLI.

## Cara fakta diverifikasi
Setiap klaim di README diambil dari kode atau konfigurasi yang ada. Saat verifikasi, tiga klaim ternyata
belum terbukti dan sudah dikoreksi:
1. Klaim "kunci tersamarkan" di `status`: tidak ada kode masking. Diganti dengan deskripsi yang sesuai bantuan perintah.
2. Nama owner private key: penjaga memeriksa `OWNER_PRIVATE_KEY`, sedangkan contoh memakai
   `BANGZEN_OWNER_PRIVATE_KEY`. Ditulis sebagai temuan, belum diperbaiki.
3. Kebenaran `intel` di Termux doc: tidak ada perintah `intel` di CLI. Dihapus.

## Temuan yang perlu ditindaklanjuti (tidak diubah di tahap ini)
- Penjaga owner private key perlu dicakup untuk kedua nama dan diuji. Tahap berikutnya.
- Belum ada tes yang memastikan keluaran `status` tidak memuat rahasia.

## Tidak berubah
- Tidak ada perubahan kode perilaku. Tes dan konfigurasi tidak disentuh.
- AI_RULES.yaml, RULES.md, SECURITY.md, RT-06, live lock, dan threshold tidak disentuh.

## Hasil
- Verifikasi cakupan README: bagian utama dan variabel kunci ditemukan.
- `scripts/run_tests.py`: TIDAK DIJALANKAN ulang. Tahap ini tidak mengubah kode, tetapi suite penuh
  tetap belum bisa dijalankan tanpa `httpx`.

## BELUM DIVERIFIKASI
- Panduan instalasi di README belum dijalankan ulang di Termux atau VPS sungguhan.
- Klaim strategi di README mengikuti kode saat ini. Belum divalidasi oleh backtest.
