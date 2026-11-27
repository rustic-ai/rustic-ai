#!/bin/sh
# POSIX‑compliant integration test runner WITHOUT coverage for faster development.
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
DB_FILE="integration_testing_app.db"

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

    printf "🚀  Starting Uvicorn (NO COVERAGE)…\n"
    opentelemetry-instrument \
        python -m rustic_ai.api_server.main \
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

    add_arg() {
        PYTEST_ARGS="$PYTEST_ARGS \"$(escape_arg "$1")\""
    }

    expand_and_add_args() {
        # Expand globs for path args only; preserve options/expressions intact.
        arg=$1
        case "$arg" in
            -*)
                add_arg "$arg"
                ;;
            *[\*\?\[]*)
                # Shell glob expansion happens here; if no matches, the pattern stays literal.
                set -- $arg
                if [ "$#" -eq 0 ]; then
                    add_arg "$arg"
                else
                    for expanded in "$@"; do
                        add_arg "$expanded"
                    done
                fi
                ;;
            *)
                add_arg "$arg"
                ;;
        esac
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
                expand_and_add_args "$1"
                shift
                ;;
        esac
    done

    # shellcheck disable=SC2086
    eval "set -- $PYTEST_ARGS"

    if [ "$PARALLEL" -eq 1 ] && [ "$HAS_XDIST" -eq 0 ] && [ "$WORKERS" = "auto" ]; then
        if command -v nproc >/dev/null 2>&1; then
            CPU_COUNT=$(nproc)
        elif command -v getconf >/dev/null 2>&1; then
            CPU_COUNT=$(getconf _NPROCESSORS_ONLN)
        else
            CPU_COUNT=1
        fi

        if [ "$CPU_COUNT" -gt 2 ]; then
            WORKERS=$((CPU_COUNT - 2))

            # Importing the complete monorepo test graph takes substantial memory
            # per worker (ML libraries in particular). Cap CPU-derived parallelism
            # to roughly one worker per 4 GiB to avoid swapping or OOM-killing the
            # test runner on memory-constrained CI hosts and container VMs.
            MEMORY_KB=0
            if [ -r /sys/fs/cgroup/memory.max ]; then
                CGROUP_MEMORY_BYTES=$(cat /sys/fs/cgroup/memory.max)
                case "$CGROUP_MEMORY_BYTES" in
                    ""|max|*[!0-9]*) ;;
                    *) MEMORY_KB=$((CGROUP_MEMORY_BYTES / 1024)) ;;
                esac
            fi
            if [ "$MEMORY_KB" -eq 0 ] && [ -r /proc/meminfo ]; then
                MEMORY_KB=$(awk "/^MemTotal:/ { print \$2; exit }" /proc/meminfo)
            fi
            if [ "$MEMORY_KB" -eq 0 ] && command -v sysctl >/dev/null 2>&1; then
                MEMORY_BYTES=$(sysctl -n hw.memsize 2>/dev/null || printf 0)
                MEMORY_KB=$((MEMORY_BYTES / 1024))
            fi

            if [ "$MEMORY_KB" -gt 0 ]; then
                MEMORY_WORKERS=$((MEMORY_KB / 4194304))
                if [ "$MEMORY_WORKERS" -lt 1 ]; then
                    MEMORY_WORKERS=1
                fi
                if [ "$WORKERS" -gt "$MEMORY_WORKERS" ]; then
                    WORKERS=$MEMORY_WORKERS
                fi
            fi

            if [ "$WORKERS" -gt 1 ]; then
                printf "⚙️  Auto-configuring workers: %d cores, %d MiB memory; using %d workers\n" \
                    "$CPU_COUNT" "$((MEMORY_KB / 1024))" "$WORKERS"
            else
                printf "ℹ️  Available memory supports one worker. Disabling parallel execution.\n"
                PARALLEL=0
            fi
        else
            printf "ℹ️  Only %d cores detected (<= 2). Disabling parallel execution.\n" "$CPU_COUNT"
            PARALLEL=0
        fi
    fi

    if [ "$PARALLEL" -eq 1 ] && [ "$HAS_XDIST" -eq 0 ]; then
        set -- -n "$WORKERS" "$@"
    fi

    if [ "$#" -eq 0 ]; then
        echo "No pytest args provided; defaulting to '.'" >&2
        set -- .
    fi

    PYTEST_BASE_ARGS="${RUSTIC_PYTEST_ARGS:-}"
    if [ -z "$PYTEST_BASE_ARGS" ]; then
        PYTEST_BASE_ARGS="-q -r a --disable-warnings"
    fi
    if [ "${RUSTIC_PYTEST_VERBOSE:-0}" = "1" ]; then
        PYTEST_BASE_ARGS="-vv $PYTEST_BASE_ARGS"
    fi
    if [ "${RUSTIC_PYTEST_SHOWLOCALS:-0}" = "1" ]; then
        PYTEST_BASE_ARGS="$PYTEST_BASE_ARGS --showlocals"
    fi

    printf "🧪  Running pytest (NO COVERAGE) with:\n"
    for arg in $PYTEST_BASE_ARGS "$@"; do
        printf "    • %s\n" "$arg"
    done

    PYTHONFAULTHANDLER=true \
        pytest $PYTEST_BASE_ARGS "$@"
' run_tests_no_coverage "$@" &
SESSION_PID=$!

# propagate pytest's exit code
wait "$SESSION_PID"
exit $?
