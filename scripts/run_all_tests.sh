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
# Kill any processes using the embedded backend port
lsof -ti:31134 | xargs -r kill -9 2>/dev/null || :
lsof -ti:8880 | xargs -r kill -9 2>/dev/null || :

# -------- cleanup on exit --------
cleanup() {
    printf '🧹  Cleaning up…\n' >&2

    if [ -n "${SESSION_PID:-}" ] && kill -0 "$SESSION_PID" 2>/dev/null; then
        echo "Killing session with PID: $SESSION_PID"
        PGID=$(ps -o pgid= -p "$SESSION_PID" | tr -d ' ')
        if [ -n "$PGID" ] && kill -0 "-$PGID" 2>/dev/null; then
            kill -TERM "-$PGID" 2>/dev/null || :
            sleep 0.2
            kill -KILL "-$PGID" 2>/dev/null || :
        fi
        pkill -9 -P "$SESSION_PID" 2>/dev/null || :   # sweep for strays
        wait "$SESSION_PID" 2>/dev/null || :
    fi

    echo "Killing any remaining processes on the embedded backend port"
    sleep 0.2   # give processes time to exit
    # Kill any remaining processes on the embedded backend port
    lsof -ti:31134 | xargs -r kill -9 2>/dev/null || :

    # Kill any remaining processes on the Uvicorn port
    sleep 1  # give Uvicorn time to exit
    echo "Killing any remaining processes on the Uvicorn port"
    lsof -ti:8880 | xargs -r kill -9 2>/dev/null || :
    pkill -f "uvicorn rustic_ai.api_server.main:app" 2>/dev/null || :


    rm -f "$DB_FILE" .test_session_pid 2>/dev/null || :
    printf '🧹  Cleanup complete.\n' >&2
}
trap cleanup EXIT INT TERM

# -------- run everything inside its own session --------
# Pass script name as $0, then all arguments
sh -c '
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

    # Arguments are already in correct positions ($1, $2, etc.)
    printf "🧪  Running pytest with: \n"
    PYTHONFAULTHANDLER=true \
    coverage run --source=. --context=TESTS \
        --data-file="coverage/coverage-tests" \
        -m pytest -vvvv --showlocals "$@"
' run_all_tests "$@" &
SESSION_PID=$!

# propagate pytest’s exit code
wait "$SESSION_PID"
exit $?
