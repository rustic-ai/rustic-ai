#!/bin/sh
# runs the passed command in each poetry project folder
set -x
set -u
set -e
DIR="$( cd "$( dirname "$0" )" && pwd )"
cd "${DIR}/.." || exit

# Capture the user's command
user_command="$*"

# all python packages, in topological order
. ${DIR}/modules.sh

# Use IFS and set to simulate an array in sh
IFS=' '
set -- $MODULES
unset IFS

# Iterate through the modules
for module in "$@"; do
  cd "${DIR}/../$module" || exit
  echo "==running in ${module}=="
  sh -c "$user_command" || true  # Ignore the exit code
done
