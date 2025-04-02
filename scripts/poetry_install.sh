#!/bin/sh
set -x
set -u
set -e

DIR="$( cd "$( dirname "$0" )" && pwd )"
cd "${DIR}/.." || exit

# all python packages, in topological order
. ${DIR}/modules.sh

poetry self add poetry-plugin-mono-repo-deps
poetry install --with dev --sync

