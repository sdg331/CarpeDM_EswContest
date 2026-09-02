#!/usr/bin/env bash
set -euo pipefail

cd "${RELIEFCHECK_HOME:-/home/pi/reliefcheck}"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

exec python3 -m reliefcheck.main \
  --host "${RELIEFCHECK_HOST:-0.0.0.0}" \
  --port "${RELIEFCHECK_PORT:-8008}"
