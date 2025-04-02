#!/bin/sh
# runs the passed command in each poetry project folder
set -x
set -u
set -e
DIR="$( cd "$( dirname "$0" )" && pwd )"
cd "${DIR}/.." || exit

# all python packages, in topological order
. ${DIR}/modules.sh
for module in "${MODULES[@]}"; do
  cd "${DIR}/../$module" || exit
  echo "==running in ${module}=="
  "$@" || true  # Ignore the exit code
done
