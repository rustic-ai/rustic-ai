#!/bin/sh
# Run in every registered module and report all failures to the caller.
set -u
[ "${VERBOSE:-0}" != "1" ] || set -x

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)" || exit 1
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)" || exit 1
if [ $# -eq 0 ]; then
  echo "Usage: $0 <command to run in each module>" >&2
  exit 1
fi
user_command="$*"
. "${SCRIPT_DIR}/modules.sh" || exit 1
if [ -z "${MODULES:-}" ]; then
  echo "No modules configured." >&2
  exit 1
fi
failures=""
for module in $MODULES; do
  echo "Processing module: ${module}"
  if (cd "${PROJECT_ROOT}/${module}" && sh -c "${user_command}"); then
    :
  else
    status=$?
    echo "Module ${module} failed with status ${status}." >&2
    failures="${failures} ${module}"
  fi
done
if [ -n "$failures" ]; then
  echo "Failed modules:${failures}" >&2
  exit 1
fi
echo "All specified modules succeeded."
