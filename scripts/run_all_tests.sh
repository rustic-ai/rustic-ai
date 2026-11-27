#!/bin/sh
# POSIX‑compliant integration test runner that leaves no stray processes.
# Optional args:
#   --parallel             Enable pytest-xdist with -n auto
#   --workers N|auto       Set xdist worker count (implies --parallel)
#   --no-parallel          Force serial execution

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

# -------- cleanup on exit --------
cleanup() {
    trap - EXIT INT TERM
    printf '🧹  Cleaning up…\n' >&2

    if [ -n "${SESSION_PID:-}" ]; then
        echo "Killing session with PID: $SESSION_PID"
        # The launcher makes SESSION_PID the process-group ID. Signal that
        # group even if its leader exited but the server is still running.
        kill -TERM "-$SESSION_PID" 2>/dev/null || kill -TERM "$SESSION_PID" 2>/dev/null || :
        sleep 0.2
        kill -KILL "-$SESSION_PID" 2>/dev/null || :
        wait "$SESSION_PID" 2>/dev/null || :
    fi

    rm -f "$DB_FILE" .test_session_pid 2>/dev/null || :
    printf '🧹  Cleanup complete.\n' >&2
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# -------- run everything inside its own session --------
# Pass script name as $0, then all arguments
python "$SCRIPT_DIR/run_in_session.py" sh -c '
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

    PARALLEL=0
    HAS_XDIST=0
    WORKERS=auto
    PYTEST_ARGS=""

    escape_arg() {
        # Escape backslashes and double-quotes for safe eval inside double quotes.
        printf "%s" "$1" | sed "s/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g"
    }

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --parallel)
                PARALLEL=1
                shift
                ;;
            --no-parallel)
                PARALLEL=0
                shift
                ;;
            --workers)
                if [ "$#" -lt 2 ]; then
                    echo "Missing value for --workers" >&2
                    exit 2
                fi
                WORKERS="$2"
                PARALLEL=1
                shift 2
                ;;
            --workers=*)
                WORKERS="${1#--workers=}"
                PARALLEL=1
                shift
                ;;
            -n|--numprocesses)
                HAS_XDIST=1
                if [ "$#" -lt 2 ]; then
                    echo "Missing value for $1" >&2
                    exit 2
                fi
                PYTEST_ARGS="$PYTEST_ARGS \"$(escape_arg "$1")\" \"$(escape_arg "$2")\""
                shift 2
                ;;
            -n*)
                HAS_XDIST=1
                PYTEST_ARGS="$PYTEST_ARGS \"$(escape_arg "$1")\""
                shift
                ;;
            *)
                PYTEST_ARGS="$PYTEST_ARGS \"$(escape_arg "$1")\""
                shift
                ;;
        esac
    done

    # shellcheck disable=SC2086
    eval "set -- $PYTEST_ARGS"

    if [ "$PARALLEL" -eq 1 ] && [ "$HAS_XDIST" -eq 0 ]; then
        set -- -n "$WORKERS" "$@"
    fi

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
