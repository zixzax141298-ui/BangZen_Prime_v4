#!/bin/bash
# Installs BangZen Prime into the active virtualenv and refuses to continue if the
# installed build is not the expected version. Run from the unzipped project folder.
set -euo pipefail
EXPECTED="0.3.0"
if [ ! -f pyproject.toml ]; then
  echo "ERROR: run this from the BangZenPrime project folder (pyproject.toml not found)" >&2
  exit 1
fi
if [ -z "${VIRTUAL_ENV:-}" ]; then
  echo "ERROR: activate your virtualenv first (source ~/bz-venv/bin/activate)" >&2
  exit 1
fi
pip install --upgrade pip >/dev/null
pip install .
GOT="$(bangzen-prime --version)"
if [ "$GOT" != "$EXPECTED" ]; then
  echo "ERROR: installed version is $GOT, expected $EXPECTED. Old files are still in use." >&2
  exit 1
fi
bangzen-prime monitor --help >/dev/null || { echo "ERROR: monitor command missing" >&2; exit 1; }
echo "OK: bangzen-prime $GOT installed with monitor command"
