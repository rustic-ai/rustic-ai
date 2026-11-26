#!/bin/sh
# Build fresh artifacts, then publish the complete aggregate in one exchange.
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PROJECT_ROOT}/dist"
. "${SCRIPT_DIR}/modules.sh"
if [ -z "${MODULES:-}" ]; then
  echo "No modules configured." >&2
  exit 1
fi
STAGING_ROOT="$(mktemp -d "${PROJECT_ROOT}/.build-artifacts.XXXXXX")"
trap 'rm -rf "${STAGING_ROOT}"' EXIT
trap 'exit 1' HUP INT TERM
AGGREGATE="${STAGING_ROOT}/aggregate"
mkdir "${AGGREGATE}"
# Keep notes, archived release directories and other non-artifact entries.
if [ -d "$DIST_DIR" ]; then
  for entry in "$DIST_DIR"/* "$DIST_DIR"/.[!.]* "$DIST_DIR"/..?*; do
    [ -e "$entry" ] || [ -L "$entry" ] || continue
    case "$entry" in
      *.whl|*.tar.gz) [ -d "$entry" ] || continue ;;
    esac
    cp -pR "$entry" "$AGGREGATE/"
  done
fi
for module in $MODULES; do
  [ "${SKIP_MODULE:-}" != "$module" ] || continue
  echo "Building module: ${module}"
  OUTPUT="${STAGING_ROOT}/${module}"
  mkdir "$OUTPUT"
  (
    cd "${PROJECT_ROOT}/${module}"
    poetry install --without dev
    poetry build --output "$OUTPUT"
  )
  wheels=0
  sources=0
  for artifact in "$OUTPUT"/*; do
    [ -f "$artifact" ] || continue
    case "$artifact" in
      *.whl) wheels=$((wheels + 1)) ;;
      *.tar.gz) sources=$((sources + 1)) ;;
      *) echo "Unexpected build output: ${artifact}" >&2; exit 1 ;;
    esac
    name="$(basename "$artifact")"
    [ ! -e "${AGGREGATE}/${name}" ] || {
      echo "Duplicate artifact name: ${name}" >&2; exit 1;
    }
    cp -p "$artifact" "${AGGREGATE}/${name}"
  done
  if [ "$wheels" -ne 1 ] || [ "$sources" -ne 1 ]; then
    echo "Module ${module} must produce one wheel and one source archive." >&2
    exit 1
  fi
done
"${BUILD_PYTHON:-python3}" "${SCRIPT_DIR}/replace_artifact_directory.py" "$AGGREGATE" "$DIST_DIR"
echo "Published fresh artifacts in ${DIST_DIR}."
