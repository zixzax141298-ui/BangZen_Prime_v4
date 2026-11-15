#!/bin/bash
# Pasang BangZen Prime di VPS Linux. Tanpa Docker dan tanpa paket native.
# Dijalankan dari folder proyek sebagai user biasa (bukan root).
# Script TIDAK memakai sudo dan TIDAK mengaktifkan service. Unit systemd hanya
# dirender ke deploy/generated/; owner memasangnya sendiri (lihat pesan di akhir).
set -euo pipefail

EXPECTED="0.3.0"
VENV_DIR="${BZ_VENV:-$HOME/bz-venv}"

if [ "$(id -u)" -eq 0 ]; then
  echo "ERROR: jangan jalankan sebagai root. Gunakan user biasa." >&2
  exit 1
fi
if [ ! -f pyproject.toml ] || [ ! -f deploy/systemd/bangzen-prime-monitor.service ]; then
  echo "ERROR: jalankan dari folder proyek BangZen Prime (pyproject.toml tidak ditemukan)." >&2
  exit 1
fi
APP_DIR="$(pwd)"
case "$APP_DIR$VENV_DIR" in
  *" "*|*"|"*) echo "ERROR: path folder dan venv tidak boleh berisi spasi atau '|' (systemd)." >&2; exit 1 ;;
esac
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "ERROR: Python 3.11 atau lebih baru diperlukan." >&2
  exit 1
fi

# Fail-closed: jika .env mengaktifkan live atau broadcast, hentikan instalasi.
if [ -f .env ] && grep -Eiq '^[[:space:]]*BANGZEN_(LIVE_TRADING|BROADCAST_ENABLED)[[:space:]]*=[[:space:]]*"?(true|1|yes)"?[[:space:]]*$' .env; then
  echo "ERROR: .env mengaktifkan live atau broadcast. Itu ditolak. Perbaiki .env dulu." >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/python" -m pip install --quiet "$APP_DIR"

GOT="$("$VENV_DIR/bin/bangzen-prime" --version)"
if [ "$GOT" != "$EXPECTED" ]; then
  echo "ERROR: versi terpasang $GOT, diharapkan $EXPECTED. Berkas lama mungkin masih dipakai." >&2
  exit 1
fi
"$VENV_DIR/bin/bangzen-prime" monitor --help >/dev/null || { echo "ERROR: perintah monitor tidak ada." >&2; exit 1; }

mkdir -p deploy/generated
UNITS="bangzen-prime-monitor.service bangzen-prime-discover.service bangzen-prime-daily-report.service bangzen-prime-daily-report.timer"
for unit in $UNITS; do
  sed -e "s|__APP_USER__|$(id -un)|g" \
      -e "s|__APP_DIR__|$APP_DIR|g" \
      -e "s|__VENV_DIR__|$VENV_DIR|g" \
      "deploy/systemd/$unit" > "deploy/generated/$unit"
  if grep -q '__[A-Z_]*__' "deploy/generated/$unit"; then
    echo "ERROR: placeholder $unit belum terisi semua." >&2
    exit 1
  fi
done

echo "OK: bangzen-prime $GOT terpasang di $VENV_DIR"
[ -f watchlist.txt ] || echo "CATATAN: watchlist.txt belum ada. Salin dari configs/watchlist.example.txt."
cat <<MSG
Unit systemd sudah dirender ke deploy/generated/, BELUM diaktifkan.
Untuk memasang (jalankan sendiri, butuh sudo):
  Monitor:
    sudo cp deploy/generated/bangzen-prime-monitor.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now bangzen-prime-monitor
  Penemuan koin terus-menerus:
    sudo cp deploy/generated/bangzen-prime-discover.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now bangzen-prime-discover
  Laporan harian (00:10 UTC):
    sudo cp deploy/generated/bangzen-prime-daily-report.service deploy/generated/bangzen-prime-daily-report.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now bangzen-prime-daily-report.timer
    systemctl list-timers bangzen-prime-daily-report.timer
MSG
