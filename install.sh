#!/usr/bin/env bash
# One-line installer (macOS / Linux / WSL / Git Bash).
#
#   curl -fsSL https://raw.githubusercontent.com/itskeshavm-sketch/make-it-local/main/install.sh | bash
#
# Downloads the toolkit, then runs setup.sh (provider wizard included).
# No git required. Safe to re-run: an existing folder is updated, not wiped.

set -euo pipefail

REPO="itskeshavm-sketch/make-it-local"
ZIP="https://codeload.github.com/$REPO/zip/refs/heads/main"
TARGET="${MAKE_IT_LOCAL_DIR:-$PWD/make-it-local}"

SKIP_DEPS=0
SKIP_PROVIDER=0
NO_VENV=0
PROVIDER_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --dir)           TARGET="$2"; shift 2 ;;
    --preset)        PROVIDER_ARGS+=(--preset "$2"); shift 2 ;;
    --base-url)      PROVIDER_ARGS+=(--base-url "$2"); shift 2 ;;
    --api-key)       PROVIDER_ARGS+=(--api-key "$2"); shift 2 ;;
    --model)         PROVIDER_ARGS+=(--model "$2"); shift 2 ;;
    --skip-deps)     SKIP_DEPS=1; shift ;;
    --skip-provider) SKIP_PROVIDER=1; shift ;;
    --no-venv)       NO_VENV=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

say()  { printf '==> %s\n' "$1"; }
ok()   { printf '    %s\n' "$1"; }
warn() { printf '    %s\n' "$1" >&2; }

say "Installing make-it-local into $TARGET"

if [ -d "$TARGET/.git" ]; then
  say "Existing git checkout found - updating"
  if git -C "$TARGET" pull --ff-only >/dev/null 2>&1; then ok "updated"; else warn "git pull failed, continuing"; fi
elif [ -d "$TARGET" ]; then
  say "Folder exists but is not a git checkout - refreshing it"
  rm -rf "$TARGET"
  mkdir -p "$TARGET"
else
  mkdir -p "$TARGET"
fi

if [ ! -d "$TARGET/.git" ]; then
  if command -v git >/dev/null 2>&1; then
    say "Cloning with git"
    git clone --depth 1 "https://github.com/$REPO.git" "$TARGET" >/dev/null
    ok "cloned"
  else
    say "git not found - downloading the zip instead"
    TMP="$(mktemp -d)"
    curl -fsSL "$ZIP" -o "$TMP/repo.zip"
    unzip -q "$TMP/repo.zip" -d "$TMP"
    INNER="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"
    cp -R "$INNER"/. "$TARGET"/
    rm -rf "$TMP"
    ok "downloaded"
  fi
fi

if [ ! -f "$TARGET/setup.sh" ]; then
  warn "setup.sh missing from the download"
  exit 1
fi

say "Running setup (provider wizard)"
SETUP_ARGS=()
[ "$SKIP_DEPS" -eq 1 ] && SETUP_ARGS+=(--skip-deps)
[ "$SKIP_PROVIDER" -eq 1 ] && SETUP_ARGS+=(--skip-provider)
[ "$NO_VENV" -eq 1 ] && SETUP_ARGS+=(--no-venv)
# shellcheck disable=SC2086
bash "$TARGET/setup.sh" "${SETUP_ARGS[@]}" ${PROVIDER_ARGS[@]+"${PROVIDER_ARGS[@]}"}

echo
echo "Installed at: $TARGET"
echo "cd \"$TARGET\" && python3 scripts/local_ai.py"
