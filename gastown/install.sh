#!/usr/bin/env bash
#
# gastown itself is brew-managed via ./Brewfile. This installer links the town
# plugins kept in ./plugins into an existing Gas Town at ~/gt.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOWN_PLUGINS="${HOME}/gt/plugins"

link_item() {
  local src="$1" dst="$2" name="$3"
  if [[ -L "$dst" ]] && [[ "$(readlink "$dst")" == "$src" ]]; then
    echo "» ${name} already linked"
  elif [[ -e "$dst" ]]; then
    echo "⚠ ${name}: ${dst} exists and is not a symlink — back up and remove manually"
  else
    ln -s "$src" "$dst"
    echo "» Linked ${name}"
  fi
}

if [[ ! -d "$TOWN_PLUGINS" ]]; then
  echo "» No Gas Town at ~/gt; skipping town plugins"
  exit 0
fi

# gt skips plugin directories that are symlinks, so each plugin gets a real
# directory and only its files are linked.
link_plugin() {
  local plugin="$1"
  shift
  mkdir -p "${TOWN_PLUGINS}/${plugin}"
  for file in "$@"; do
    link_item "${SCRIPT_DIR}/plugins/${plugin}/${file}" "${TOWN_PLUGINS}/${plugin}/${file}" "${plugin}/${file}"
  done
}

link_plugin riv-relay plugin.md relay.py
link_plugin review-inbox plugin.md review_inbox.py
