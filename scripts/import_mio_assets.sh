#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-/Users/shunsukeniwa/Projects/codex/output/hatch-pet/mio/qa/previews}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${PROJECT_DIR}/assets/miochan"

required=(
  failed.gif
  idle.gif
  jumping.gif
  review.gif
  running-left.gif
  running-right.gif
  running.gif
  waiting.gif
  waving.gif
)

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "Mio asset directory not found: ${SOURCE_DIR}" >&2
  echo "Pass a directory explicitly: scripts/import_mio_assets.sh /path/to/previews" >&2
  exit 2
fi

mkdir -p "${TARGET_DIR}"

missing=0
for filename in "${required[@]}"; do
  if [[ -f "${SOURCE_DIR}/${filename}" ]]; then
    cp "${SOURCE_DIR}/${filename}" "${TARGET_DIR}/${filename}"
    echo "Imported ${filename}"
  else
    echo "Missing ${filename}" >&2
    missing=1
  fi
done

if [[ "${missing}" -ne 0 ]]; then
  echo "Some GIFs were not imported. The CSS fallback remains available." >&2
  exit 3
fi

echo "Mio animation set is ready in ${TARGET_DIR}"

