#!/usr/bin/env bash
# One-command setup (macOS / Linux / WSL / Git Bash).
#
#   ./setup.sh
#   ./setup.sh --preset groq
#   ./setup.sh --skip-provider
#
# Creates a virtualenv if there is anything to install, then runs the provider
# wizard. Zero dependencies in the template itself, so the venv step is skipped
# automatically when requirements.txt is empty.

set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-}"
VENV_DIR=".venv"
SKIP_PROVIDER=0
SKIP_DEPS=0
NO_VENV=0
PROVIDER_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --preset)        PROVIDER_ARGS+=(--preset "$2"); shift 2 ;;
    --base-url)      PROVIDER_ARGS+=(--base-url "$2"); shift 2 ;;
    --api-key)       PROVIDER_ARGS+=(--api-key "$2"); shift 2 ;;
    --model)         PROVIDER_ARGS+=(--model "$2"); shift 2 ;;
    --skip-provider) SKIP_PROVIDER=1; shift ;;
    --skip-deps)     SKIP_DEPS=1; shift ;;
    --no-venv)       NO_VENV=1; shift ;;
    --python)        PY="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

find_python() {
  if [ -n "$PY" ]; then echo "$PY"; return; fi
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then echo "$candidate"; return; fi
  done
  echo ""
}

PY_BIN="$(find_python)"
if [ -z "$PY_BIN" ]; then
  echo "Python 3 not found. Install it and retry." >&2
  exit 1
fi
echo "==> Python: $PY_BIN"

HAS_DEPS=0
if [ -f requirements.txt ] && [ "$SKIP_DEPS" -eq 0 ]; then
  if grep -qE '^[[:space:]]*[^#[:space:]]' requirements.txt; then HAS_DEPS=1; fi
fi

PYTHON="$PY_BIN"
if [ "$HAS_DEPS" -eq 1 ]; then
  if [ "$NO_VENV" -eq 1 ]; then
    echo "==> Installing dependencies into system Python"
    "$PY_BIN" -m pip install -r requirements.txt
  else
    if [ ! -d "$VENV_DIR" ]; then
      echo "==> Creating virtualenv $VENV_DIR"
      "$PY_BIN" -m venv "$VENV_DIR"
    fi
    PYTHON="$VENV_DIR/bin/python"
    echo "==> Installing dependencies"
    "$PYTHON" -m pip install -r requirements.txt
  fi
  echo "    dependencies installed"
else
  echo "    no dependencies to install"
fi

if [ "$SKIP_PROVIDER" -eq 0 ]; then
  echo "==> AI provider setup"
  # shellcheck disable=SC2086
  "$PYTHON" scripts/setup_provider.py "${PROVIDER_ARGS[@]}"
fi

echo ""
echo "Done."
echo "  python scripts/local_ai.py        # check the provider and ping it"
echo "  python examples/hello_local_ai.py"
