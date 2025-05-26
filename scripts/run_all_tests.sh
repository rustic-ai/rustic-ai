#!/bin/sh
# POSIX-compliant test runner

# ───────────────────── strict mode ─────────────────────
set -eu         # -e aborts on error, -u on unset var
IFS=$(printf ' \t\n')   # safe IFS

# ───────────────── locate project root ─────────────────
# directory that holds this script
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# project root is the parent of scripts/
PROJECT_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)

printf '🏗  PROJECT_ROOT: %s\n' "${PROJECT_ROOT}"
cd "${PROJECT_ROOT}"

# ───────────────── cleanup on exit ─────────────────────
cleanup() {
    printf '🧹  Cleaning up…\n'
    if [ -n "${UVICORN_PID:-}" ]; then
        kill "${UVICORN_PID}" 2>/dev/null || :
        wait "${UVICORN_PID}" 2>/dev/null || :
    fi
    rm -f integration_testing_app.db
}
trap cleanup EXIT INT TERM

# ───────────────── kill stray servers ──────────────────
pkill -f "uvicorn rustic_ai.api_server.main:app" 2>/dev/null || :

# ───────────────── coverage workspace ──────────────────
COVERAGE_DIR="${PROJECT_ROOT}/coverage"
rm -rf "${COVERAGE_DIR}"
mkdir -p "${COVERAGE_DIR}"

# ───────────────── start Uvicorn ───────────────────────
export OTEL_TRACES_EXPORTER=console
export OTEL_SERVICE_NAME=GuildCommunicationService
RUSTIC_METASTORE="sqlite:///integration_testing_app.db"

printf '🚀  Starting Uvicorn…\n'
opentelemetry-instrument \
  coverage run --source=. --context=INTEGRATION \
  --data-file="${COVERAGE_DIR}/coverage-int" \
  -m rustic_ai.api_server.main \
  > uvicorn_output.txt 2>&1 &
UVICORN_PID=$!
printf '   • Uvicorn PID: %s\n' "${UVICORN_PID}"

sleep 5   # give server time to start

# ───────────────── run tests ───────────────────────────
printf '🧪  Running pytest…\n'
PYTHONFAULTHANDLER=true \
coverage run --source=. --context=TESTS \
  --data-file="${COVERAGE_DIR}/coverage-tests" \
  -m pytest -vvvv --showlocals "$@"

printf '✅  Tests completed successfully.\n'
# cleanup() will be executed automatically by trap
exit 0
