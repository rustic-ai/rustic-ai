#!/bin/sh
# Build all modules in this project

set -x
set -u
set -e

DIR="$( cd "$( dirname "$0" )" && pwd )"
cd "${DIR}/.." || exit

mkdir -p dist
poetry install --with dev --all-extras --sync

. ${DIR}/modules.sh

for module in "${MODULES[@]}"; do
  echo "Processing module: $module"
  cd "${DIR}/../$module" || exit

  # Build package
  poetry build

  poetry export -f requirements.txt --output ./dist/requirements.txt --without-hashes --with-credentials
  cp ./dist/*.whl ${DIR}/../dist/
  cp ./dist/*.tar.gz ${DIR}/../dist/
done
