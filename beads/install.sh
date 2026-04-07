#!/usr/bin/env bash
#
# Build and install beads from a dedicated release clone pinned to origin/main.
# Keeps the work repo (~/Development/src/...) independent for development.

BEADS_SRC="${HOME}/.local/src/beads"
BEADS_REMOTE="https://github.com/steveyegge/beads.git"

# Bootstrap: clone if the release copy doesn't exist yet
if [ ! -d "$BEADS_SRC" ]; then
  echo "» Cloning beads release copy..."
  mkdir -p "$(dirname "$BEADS_SRC")"
  git clone "$BEADS_REMOTE" "$BEADS_SRC"
fi

# Always build from origin/main
cd "$BEADS_SRC" || exit 1
git fetch origin main --quiet
git checkout --detach origin/main --quiet

echo "» Building beads from source ($(git rev-parse --short HEAD))..."
SKIP_UPDATE_CHECK=1 make install

if command -v bd > /dev/null 2>&1; then
  echo "» beads $(bd version 2>&1 | head -1)"
else
  echo "⚠ beads (bd) not found on PATH after install"
fi
