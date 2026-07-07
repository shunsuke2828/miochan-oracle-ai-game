#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_DIR}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export MIO_HOST="${MIO_HOST:-0.0.0.0}"
export MIO_PORT="${MIO_PORT:-4317}"

if [[ "${MIO_DATA_MODE:-auto}" == "adb" && -z "${MIO_ADB_PASSWORD:-}" && -t 0 ]]; then
  read -r -s -p "ADB password: " MIO_ADB_PASSWORD
  echo
  export MIO_ADB_PASSWORD
fi

exec python3 -m uvicorn app.main:app \
  --host "${MIO_HOST}" \
  --port "${MIO_PORT}" \
  --no-access-log
