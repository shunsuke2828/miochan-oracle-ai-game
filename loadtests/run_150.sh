#!/usr/bin/env bash
set -euo pipefail

: "${BASE_URL:?BASE_URL is required}"
: "${RUN_ID:?RUN_ID is required}"
: "${RUN_PREFIX:?RUN_PREFIX is required}"
: "${GAME_START_EPOCH_MS:?GAME_START_EPOCH_MS is required}"
: "${HOLD_UNTIL_EPOCH_MS:?HOLD_UNTIL_EPOCH_MS is required}"

RESULT_DIR="${RESULT_DIR:-/home/opc/miochan-loadtest/results}"
SCRIPT_PATH="${SCRIPT_PATH:-/home/opc/miochan-loadtest/miochan_150.js}"
mkdir -p "${RESULT_DIR}"

exec >"${RESULT_DIR}/${RUN_ID}.log" 2>&1
exec k6 run \
  --tag "testid=${RUN_ID}" \
  --summary-export "${RESULT_DIR}/${RUN_ID}-summary.json" \
  --out "json=${RESULT_DIR}/${RUN_ID}-raw.json" \
  -e "BASE_URL=${BASE_URL}" \
  -e "RUN_ID=${RUN_ID}" \
  -e "RUN_PREFIX=${RUN_PREFIX}" \
  -e "VUS=${VUS:-150}" \
  -e "STAGGER=${STAGGER:-true}" \
  -e "GAME_START_EPOCH_MS=${GAME_START_EPOCH_MS}" \
  -e "HOLD_UNTIL_EPOCH_MS=${HOLD_UNTIL_EPOCH_MS}" \
  "${SCRIPT_PATH}"
