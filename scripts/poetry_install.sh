#!/bin/sh
set -x
set -u
set -e

DIR="$( cd "$( dirname "$0" )" && pwd )"
cd "${DIR}/.." || exit

poetry self add poetry-plugin-mono-repo-deps@0.3.2
poetry install --without dev --all-extras --sync

