#!/bin/sh
# POSIX‑compliant integration test runner that leaves no stray processes.

# -------- strict mode --------
set -eu                           # exit on error or unset var
IFS=$(printf ' \t\n')

# -------- locate project root --------
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_ROOT"

# -------- paths --------
COVERAGE_DIR="$PROJECT_ROOT/coverage"
DB_FILE="integration_testing_app.db"

# -------- pre‑run cleanup --------
rm -rf "$COVERAGE_DIR"
mkdir -p "$COVERAGE_DIR"
pkill -f "uvicorn rustic_ai.api_server.main:app" 2>/dev/null || :

# -------- cleanup on exit --------
cleanup() {
    printf '🧹  Cleaning up…\n' >&2

    if [ -n "${SESSION_PID:-}" ] && kill -0 "$SESSION_PID" 2>/dev/null; then
        PGID=$(ps -o pgid= -p "$SESSION_PID" | tr -d ' ')
        if [ -n "$PGID" ] && kill -0 "-$PGID" 2>/dev/null; then
            kill -TERM "-$PGID" 2>/dev/null || :
            sleep 0.2
            kill -KILL "-$PGID" 2>/dev/null || :
        fi
        pkill -9 -P "$SESSION_PID" 2>/dev/null || :   # sweep for strays
        wait "$SESSION_PID" 2>/dev/null || :
    fi

    rm -f "$DB_FILE" .test_session_pid 2>/dev/null || :
    printf '🧹  Cleanup complete.\n' >&2
}
trap cleanup EXIT INT TERM

# -------- run everything inside its own session --------
setsid sh -c '
    echo $$ > .test_session_pid     # session leader PID for cleanup

    export OTEL_TRACES_EXPORTER=console
    export OTEL_SERVICE_NAME=GuildCommunicationService
    export RUSTIC_METASTORE="sqlite:///integration_testing_app.db"

    printf "🚀  Starting Uvicorn…\n"
    opentelemetry-instrument \
        coverage run --source=. --context=INTEGRATION \
        --data-file="coverage/coverage-int" \
        -m rustic_ai.api_server.main \
        > uvicorn_output.txt 2>&1 &
    UVICORN_PID=$!
    printf "    • Uvicorn PID: %s\n" "$UVICORN_PID"

    sleep 5   # let the server bind

    printf "🧪  Running pytest…\n"
    PYTHONFAULTHANDLER=true \
    coverage run --source=. --context=TESTS \
        --data-file="coverage/coverage-tests" \
        -m pytest -vvvv --showlocals "$@"
' "$@" &
SESSION_PID=$!

# propagate pytest’s exit code
wait "$SESSION_PID"
exit $?
