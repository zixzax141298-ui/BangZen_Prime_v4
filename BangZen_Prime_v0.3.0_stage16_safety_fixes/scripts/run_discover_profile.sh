#!/bin/bash
# Jalankan penemuan koin terus-menerus dengan profil: termux_light atau vps_default.
# Paper dan signal only. Penemuan tidak membuka order. Hentikan dengan Ctrl+C.
# Usage (dari folder proyek, venv sudah aktif): scripts/run_discover_profile.sh termux_light
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

echo "profil=$PROFILE discover interval=${BZ_DISCOVER_INTERVAL_SECONDS}s limit=$BZ_DISCOVER_LIMIT (paper only)"
exec bangzen-prime discover \
  --interval-seconds "$BZ_DISCOVER_INTERVAL_SECONDS" \
  --limit "$BZ_DISCOVER_LIMIT"
