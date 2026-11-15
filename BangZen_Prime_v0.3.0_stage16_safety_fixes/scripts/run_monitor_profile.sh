#!/bin/bash
# Jalankan monitor paper-only dengan profil: termux_light atau vps_default.
# Usage (dari folder proyek, venv sudah aktif): scripts/run_monitor_profile.sh termux_light
set -euo pipefail

PROFILE="${1:-}"
case "$PROFILE" in
  termux_light|vps_default) ;;
  *) echo "usage: $0 termux_light|vps_default" >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE_FILE="$ROOT/deploy/profiles/$PROFILE.env"
if [ ! -f "$PROFILE_FILE" ]; then
  echo "ERROR: profil tidak ditemukan: $PROFILE_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$PROFILE_FILE"

if ! command -v bangzen-prime >/dev/null 2>&1; then
  echo "ERROR: bangzen-prime tidak ada di PATH. Aktifkan venv dulu." >&2
  exit 1
fi
if [ ! -f "$BZ_WATCHLIST" ]; then
  echo "ERROR: $BZ_WATCHLIST tidak ada. Salin dari configs/watchlist.example.txt." >&2
  exit 1
fi
COUNT="$(grep -Evc '^[[:space:]]*(#|$)' "$BZ_WATCHLIST" || true)"
if [ "$COUNT" -gt "$BZ_MAX_MINTS" ]; then
  echo "ERROR: watchlist berisi $COUNT mint, profil $PROFILE membatasi $BZ_MAX_MINTS." >&2
  exit 1
fi

echo "profil=$PROFILE interval=${BZ_INTERVAL_SECONDS}s scans_per_minute=$BZ_SCANS_PER_MINUTE mint=$COUNT (paper only)"
exec bangzen-prime monitor --watchlist "$BZ_WATCHLIST" \
  --interval-seconds "$BZ_INTERVAL_SECONDS" \
  --scans-per-minute "$BZ_SCANS_PER_MINUTE"
