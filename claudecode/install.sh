#!/usr/bin/env bash

set -Eeuo pipefail
trap cleanup SIGINT SIGTERM ERR EXIT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${HOME}/.claude"

cleanup() {
  trap - SIGINT SIGTERM ERR EXIT
}

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

mkdir -p "${CLAUDE_HOME}"
mkdir -p "${CLAUDE_HOME}/session-logs"

link_item "${SCRIPT_DIR}/CLAUDE.md"      "${CLAUDE_HOME}/CLAUDE.md"      "CLAUDE.md"
link_item "${SCRIPT_DIR}/settings.json"  "${CLAUDE_HOME}/settings.json"  "settings.json"
link_item "${SCRIPT_DIR}/hooks"          "${CLAUDE_HOME}/hooks"          "hooks/"
link_item "${SCRIPT_DIR}/commands"       "${CLAUDE_HOME}/commands"       "commands/"
link_item "${SCRIPT_DIR}/skills"         "${CLAUDE_HOME}/skills"         "skills/"

# Merge knowledge index MCP config into .mcp.json if configured
# Set CLAUDE_KNOWLEDGE_INDEX_BIN to the binary name of your knowledge index tool
# (e.g., a semantic search tool that supports MCP stdio transport).
# The tool must accept "serve stdio" as arguments.
KNOWLEDGE_BIN="${CLAUDE_KNOWLEDGE_INDEX_BIN:-}"

if [[ -n "$KNOWLEDGE_BIN" ]] && command -v "$KNOWLEDGE_BIN" > /dev/null 2>&1; then
  MCP_FILE="${CLAUDE_HOME}/.mcp.json"
  MCP_KEY=".mcpServers.knowledge_index"

  if [[ -f "$MCP_FILE" ]]; then
    if jq -e "$MCP_KEY" "$MCP_FILE" > /dev/null 2>&1; then
      echo "» Knowledge index MCP already configured"
    else
      jq "${MCP_KEY} = {\"command\": \"${KNOWLEDGE_BIN}\", \"args\": [\"serve\", \"stdio\"]}" \
        "$MCP_FILE" > "${MCP_FILE}.tmp" && mv "${MCP_FILE}.tmp" "$MCP_FILE"
      echo "» Added knowledge index MCP to .mcp.json"
    fi
  else
    printf '{"mcpServers":{"knowledge_index":{"command":"%s","args":["serve","stdio"]}}}' \
      "$KNOWLEDGE_BIN" | jq . > "$MCP_FILE"
    echo "» Created .mcp.json with knowledge index MCP"
  fi
fi
