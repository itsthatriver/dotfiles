#!/usr/bin/env bash
#
# DISABLED 2026-04-28 — gascity and beads moved to brew-managed installs.
# This installer used to symlink com.jostevens.daily-update.plist into
# ~/Library/LaunchAgents and bootstrap a 5 AM source-build job for both
# tools. Now that brew owns the binaries, the daily source build would
# clobber the brew installs in ~/.local/bin, so the agent stays disabled.
#
# To re-enable: uncomment the block below and run script/install.

set -Eeuo pipefail

# SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# PLIST="com.jostevens.daily-update.plist"
# SRC="${SCRIPT_DIR}/${PLIST}"
# DST="${HOME}/Library/LaunchAgents/${PLIST}"
#
# # Unload existing job if loaded (ignore errors if not loaded)
# launchctl bootout "gui/$(id -u)/${PLIST%.plist}" 2>/dev/null || true
#
# # Symlink plist into LaunchAgents
# mkdir -p "$(dirname "$DST")"
# if [[ -L "$DST" ]] && [[ "$(readlink "$DST")" == "$SRC" ]]; then
#   echo "» ${PLIST} already linked"
# else
#   ln -sf "$SRC" "$DST"
#   echo "» Linked ${PLIST}"
# fi
#
# # Load the agent
# launchctl bootstrap "gui/$(id -u)" "$DST"
# echo "» Loaded ${PLIST}"
# echo "» Daily update runs at 05:00 local time"
