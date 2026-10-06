#!/usr/bin/env bash
# Explicit, network-enabled setup for local agents and CI. Never called by check.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  printf 'Usage: bash scripts/setup-tools.sh ENVIRONMENT_PATH\n' >&2
  exit 4
fi
setup_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -n "${GAUNTLET_PYTHON:-}" ]; then
  setup_python="$GAUNTLET_PYTHON"
elif command -v python3.12 >/dev/null 2>&1; then
  setup_python=python3.12
else
  setup_python=python3
fi
"$setup_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "Gauntlet setup requires Python 3.12+; set GAUNTLET_PYTHON to a compatible interpreter")'
"$setup_python" -m venv "$1"
environment_path="$(cd "$1" && pwd)"
"$environment_path/bin/python" -m pip install \
  -r "$setup_root/requirements-tools.txt" "$setup_root"
"$environment_path/bin/python" -c \
  'from tree_sitter_language_pack import prefetch; prefetch(["python", "typescript", "tsx", "javascript", "go", "rust", "java", "clojure"])'
for tool in gauntlet crapper mutator dryer; do
  if [ ! -x "$environment_path/bin/$tool" ]; then
    printf 'Setup did not provide %s in %s/bin\n' "$tool" "$environment_path" >&2
    exit 5
  fi
done
printf 'Quality tools ready. Activate %s/bin/activate in your shell.\n' "$environment_path"
