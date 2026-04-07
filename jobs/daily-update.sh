#!/usr/bin/env bash
#
# Daily source-build update for beads and gascity.
# Intended to run via launchd — sets up its own PATH since launchd's env is bare.

set -Eeuo pipefail

# Minimal PATH for builds: Homebrew, mise shims, and local bin
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.local/share/mise/shims:${HOME}/.local/bin:/usr/bin:/bin"

LOG_DIR="${HOME}/.local/log"
LOG_FILE="${LOG_DIR}/daily-update-$(date +%Y-%m-%d).log"
mkdir -p "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== daily-update started at $(date) ==="

DOTFILES="${HOME}/.dotfiles"
failed=()

for topic in beads gascity; do
  script="${DOTFILES}/${topic}/install.sh"
  if [[ -x "$script" ]]; then
    echo "--- ${topic} ---"
    if ! bash "$script"; then
      failed+=("$topic")
    fi
  else
    echo "⚠ ${script} not found or not executable"
    failed+=("$topic")
  fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
  echo "=== FAILED: ${failed[*]} ==="
  exit 1
fi

echo "=== daily-update finished at $(date) ==="
