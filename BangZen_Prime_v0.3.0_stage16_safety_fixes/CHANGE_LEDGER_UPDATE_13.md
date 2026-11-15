# CHANGE LEDGER UPDATE 13 — Penemuan koin terus-menerus (paper only)

## Konteks
Perintah `discover` sudah ada dan berjalan terus. Tahap ini tidak mengubah logika pencarian.
Yang ditambahkan adalah cara menjalankannya sebagai layanan jangka panjang dan profil ringan.

## Ditambahkan
- `deploy/systemd/bangzen-prime-discover.service`: template unit untuk `discover`, `Restart=on-failure`.
- `scripts/run_discover_profile.sh`: runner profil. Menolak profil tidak dikenal (exit 2) dan menolak
  jika `bangzen-prime` tidak ada di PATH.
- `docs/CONTINUOUS_DISCOVERY.md`: cara kerja, cara menjalankan, dan batasannya.
- Tes baru di `tests/unit/test_deploy_artifacts.py` (9 tes): unit discover paper only, argumen sama
  dengan profil VPS, batas CLI untuk profil discover, profil Termux lebih ringan, installer merender unit,
  dan runner menolak profil tak dikenal serta tanpa PATH.

## Diubah
- `deploy/profiles/vps_default.env`: `BZ_DISCOVER_INTERVAL_SECONDS=60`, `BZ_DISCOVER_LIMIT=30`.
- `deploy/profiles/termux_light.env`: `BZ_DISCOVER_INTERVAL_SECONDS=600`, `BZ_DISCOVER_LIMIT=10`.
- `scripts/install_vps.sh`: merender unit discover dan menampilkan perintah pemasangannya.
- `docs/TERMUX.md`: bagian penemuan koin.

## Hasil
- `tests/unit/test_deploy_artifacts.py`: 30 lulus, 0 gagal.
- `systemd-analyze verify` pada unit discover yang sudah dirender (stub sementara, sudah dihapus): exit 0.
- `bash -n` pada runner dan installer: bersih.
- Runner diuji untuk jalur gagal: profil tak dikenal dan tanpa PATH.
- `scripts/run_tests.py`: TIDAK DIJALANKAN (`httpx` belum terpasang, tidak ada jaringan).

## BELUM DIVERIFIKASI
- Loop `discover` berjalan terus di VPS nyata, termasuk pemulihan setelah gagal.
- Hasil penemuan dari DexScreener nyata. Sandbox tidak punya jaringan, jadi tidak ada panggilan sungguhan.
- Batas rate limit DexScreener dalam kondisi nyata.
- Penemuan di Termux, termasuk menjaga proses tetap hidup.

## Batasan yang tersisa
- Satu sumber penemuan (DexScreener). Tidak ada sumber kedua.
- Penemuan tidak menyaring token mati, rug, atau delisted secara historis. Itu item 1 dan butuh data dari owner.
- Penemuan tidak memakai watchlist. Kandidat yang lolos hanya menghasilkan sinyal paper.
