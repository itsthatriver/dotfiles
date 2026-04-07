#!/usr/bin/env bash
#
# Symlink the LaunchAgent plist and load it.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST="com.jostevens.daily-update.plist"
SRC="${SCRIPT_DIR}/${PLIST}"
DST="${HOME}/Library/LaunchAgents/${PLIST}"

# Unload existing job if loaded (ignore errors if not loaded)
launchctl bootout "gui/$(id -u)/${PLIST%.plist}" 2>/dev/null || true

# Symlink plist into LaunchAgents
mkdir -p "$(dirname "$DST")"
if [[ -L "$DST" ]] && [[ "$(readlink "$DST")" == "$SRC" ]]; then
  echo "» ${PLIST} already linked"
else
  ln -sf "$SRC" "$DST"
  echo "» Linked ${PLIST}"
fi

# Load the agent
launchctl bootstrap "gui/$(id -u)" "$DST"
echo "» Loaded ${PLIST}"
echo "» Daily update runs at 05:00 local time"
