#!/usr/bin/env bash
# gastown/install.sh — Install Gas Town personal formula library
#
# Symlinks formulas from this topic into ~/.beads/formulas/ so they are
# discoverable by `bd formula list` and `gt formula list` without requiring
# manual copying. The beads search path includes ~/.beads/formulas/ by default.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORMULAS_SRC="${SCRIPT_DIR}/formulas"
FORMULAS_DST="${HOME}/.beads/formulas"

cleanup() {
  trap - SIGINT SIGTERM ERR EXIT
}
trap cleanup SIGINT SIGTERM ERR EXIT

link_formula() {
  local src="$1"
  local name
  name="$(basename "$src")"
  local dst="${FORMULAS_DST}/${name}"

  if [[ -L "$dst" ]] && [[ "$(readlink "$dst")" == "$src" ]]; then
    echo "» ${name} already linked"
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
