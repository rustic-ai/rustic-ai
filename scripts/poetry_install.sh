#!/bin/sh
set -x
set -u
set -e

DIR="$( cd "$( dirname "$0" )" && pwd )"
cd "${DIR}/.." || exit

poetry self add poetry-plugin-mono-repo-deps
poetry install --without dev --sync

