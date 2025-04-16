#!/bin/sh
# Build all modules in this project

set -x
set -u
set -e

DIR="$( cd "$( dirname "$0" )" && pwd )"
cd "${DIR}/.." || exit

mkdir -p dist


. ${DIR}/modules.sh

# Use IFS and set to simulate an array in sh
IFS=' '
set -- $MODULES
unset IFS

# Iterate through the modules
for module in "$@"; do
  # Check if the module should be skipped
  if [ "${SKIP_MODULE}" != "" ] && [ "$module" = "${SKIP_MODULE}" ]; then
    echo "Skipping module: $module"
    continue
  fi

  echo "Processing module: $module"
  cd "${DIR}/../$module" || exit

  poetry install --without dev
  # Build package
  poetry build

  cp ./dist/*.whl ${DIR}/../dist/
  cp ./dist/*.tar.gz ${DIR}/../dist/
done
