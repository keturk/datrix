#!/usr/bin/env bash
# Rendered from scripts/common/templates/entrypoint.sh, as is every line from here on: the POSIX twin of the
# .ps1 wrapper beside it. It runs the Python module named below in the shared venv with the arguments given
# (the module's --kebab-name flags), as an argument vector, and exits with the module's exit code.
set -u
module="datrix_scripts.scan.dgen_census"
scripts="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ ! -d "$scripts/common/lib/datrix_scripts" ]; do
  [ "$scripts" = "/" ] && { echo "No datrix/scripts tree holds $0. Expected <workspace>/datrix/scripts; run the wrapper from there." >&2; exit 1; }
  scripts="$(dirname "$scripts")"
done
workspace="$(dirname "$(dirname "$scripts")")"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) bin="$workspace/.venv/Scripts"; python="$bin/python.exe"; sep=";"; native() { cygpath -w "$1"; } ;;
  *) bin="$workspace/.venv/bin"; python="$bin/python"; sep=":"; native() { printf '%s' "$1"; } ;;
esac
export PYTHONPATH="$(native "$scripts/common/lib")${PYTHONPATH:+$sep$PYTHONPATH}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$(native "$workspace/.pycache-verify")}"
unset PYTHONHOME
if [ ! -x "$python" ]; then
  bootstrap="${DATRIX_PYTHON:-}"
  for candidate in py python3 python; do
    [ -n "$bootstrap" ] && break
    found="$(command -v "$candidate" || true)"
    case "$found" in ""|*/WindowsApps/*) ;; *) bootstrap="$found" ;; esac
  done
  [ -n "$bootstrap" ] || { echo "No Python was found to create the shared venv at $workspace/.venv. Expected DATRIX_PYTHON or one of py, python3, python on PATH. Fix: install a CPython built for this machine's CPU, or set DATRIX_PYTHON to one, then retry." >&2; exit 1; }
  "$bootstrap" -m datrix_scripts.venv --ensure || exit $?
fi
export VIRTUAL_ENV="$(native "$workspace/.venv")" PATH="$bin:$PATH"
exec "$python" -m "$module" "$@"
