#!/usr/bin/env bash
#
# Build and install gascity from a dedicated release clone pinned to origin/main.
# Keeps the work repo (~/Development/src/...) independent for development.

GASCITY_SRC="${HOME}/.local/src/gascity"
GASCITY_REMOTE="https://github.com/gastownhall/gascity.git"

# Bootstrap: clone if the release copy doesn't exist yet
if [ ! -d "$GASCITY_SRC" ]; then
  echo "» Cloning gascity release copy..."
  mkdir -p "$(dirname "$GASCITY_SRC")"
  git clone "$GASCITY_REMOTE" "$GASCITY_SRC"
fi

# Always build from origin/main
cd "$GASCITY_SRC" || exit 1
git fetch origin main --quiet
git checkout --detach origin/main --quiet

echo "» Building gascity from source ($(git rev-parse --short HEAD))..."
make install

if command -v gc > /dev/null 2>&1; then
  echo "» gascity $(gc version 2>&1 | head -1)"
else
  echo "⚠ gascity (gc) not found on PATH after install"
fi
