#!/usr/bin/env bash
# gastown/install.sh — Install Gas Town personal formula library and post-brew setup
#
# 1. Symlinks formulas from this topic into ~/.beads/formulas/ so they are
#    discoverable by `bd formula list` and `gt formula list`.
# 2. Configures Dolt identity from git config.
# 3. Installs Go via mise.
# 4. Verifies all dependencies are on PATH.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORMULAS_SRC="${SCRIPT_DIR}/formulas"
FORMULAS_DST="${HOME}/.beads/formulas"

cleanup() {
  trap - SIGINT SIGTERM ERR EXIT
}
trap cleanup SIGINT SIGTERM ERR EXIT

# --- Formula library ---

link_formula() {
  local src="$1"
  local name
  name="$(basename "$src")"
  local dst="${FORMULAS_DST}/${name}"

  if [[ -L "$dst" ]] && [[ "$(readlink "$dst")" == "$src" ]]; then
    echo "» ${name} already linked"
  elif [[ -L "$dst" ]]; then
    # Symlink exists but points elsewhere — update it
    ln -sf "$src" "$dst"
    echo "» Relinked ${name}"
  elif [[ -e "$dst" ]]; then
    echo "⚠ ${name}: ${dst} exists and is not a symlink — back up and remove manually"
  else
    ln -s "$src" "$dst"
    echo "» Linked ${name}"
  fi
}

mkdir -p "${FORMULAS_DST}"

for formula in "${FORMULAS_SRC}"/*.formula.toml; do
  [[ -e "$formula" ]] || continue
  link_formula "$formula"
done

echo "✓ Gas Town formula library installed"

# --- Dolt identity (mirrors git config) ---
if command -v dolt > /dev/null 2>&1; then
  git_name="$(git config user.name 2>/dev/null || true)"
  git_email="$(git config user.email 2>/dev/null || true)"

  if [[ -n "$git_name" ]]; then
    dolt config --global --set user.name "$git_name"
    echo "» Dolt user.name set to: $git_name"
  else
    echo "» Warning: git user.name not set — run 'dolt config --global --set user.name \"Your Name\"'"
  fi

  if [[ -n "$git_email" ]]; then
    dolt config --global --set user.email "$git_email"
    echo "» Dolt user.email set to: $git_email"
  else
    echo "» Warning: git user.email not set — run 'dolt config --global --set user.email you@example.com'"
  fi
fi

# --- Go via mise ---
if command -v mise > /dev/null 2>&1; then
  echo "» Installing Go via mise"
  mise use --global go@latest
fi

# --- Verify dependencies ---
missing=()
for cmd in dolt gt bd tmux sqlite3 go; do
  if ! command -v "$cmd" > /dev/null 2>&1; then
    missing+=("$cmd")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "» Warning: missing commands: ${missing[*]}"
else
  echo "» All Gastown dependencies verified"
fi

echo ""
echo "» Next step: run 'gt install ~/gt' to initialize Gastown"
