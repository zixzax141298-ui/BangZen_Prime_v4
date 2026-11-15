# Penemuan koin terus-menerus

## Cara kerja
`bangzen-prime discover` adalah loop tanpa henti. Setiap siklus mengambil kandidat baru dari DexScreener,
melewatkan kandidat yang baru saja dipindai (cooldown tersimpan di database), lalu memindai sisanya.
Kandidat yang lolos menghasilkan sinyal paper dan notifikasi lewat jalur outbox yang sudah ada.
Tidak ada order live dan tidak ada broadcast. Loop berhenti jika emergency stop aktif (`HALT.flag`
atau `BANGZEN_EMERGENCY_STOP=true`).

## Menjalankan
    bangzen-prime discover --interval-seconds 60 --limit 30        # VPS, terus-menerus
    scripts/run_discover_profile.sh vps_default                    # sama, dari profil
    scripts/run_discover_profile.sh termux_light                   # profil ringan

## Sebagai layanan VPS
`scripts/install_vps.sh` merender `bangzen-prime-discover.service`. Pemasangan dijalankan sendiri dengan sudo:

    sudo cp deploy/generated/bangzen-prime-discover.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now bangzen-prime-discover
    journalctl -u bangzen-prime-discover -f

Unit ini memakai `Restart=on-failure`, karena loop harus tetap hidup.

## Batasan
- Penemuan memakai satu sumber (DexScreener). Kualitas dan kelengkapannya belum diukur.
- Sumber ini bisa kena rate limit. Anggaran panggilan per menit dibatasi di kode, tetapi batas nyata
  dari DexScreener belum diuji.
- Penemuan mencari kandidat baru. Ia tidak menggantikan watchlist untuk monitor, dan tidak menjamin
  kandidat yang ditemukan layak. Sinyal tetap berupa riset, bukan instruksi trading.
- Kandidat tidak diberi label rug atau token mati secara historis. Itu butuh data point-in-time (item 1),
  yang masih menunggu sumber data dari owner.
