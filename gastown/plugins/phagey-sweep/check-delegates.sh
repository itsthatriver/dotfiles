#!/usr/bin/env bash
# Liveness check for the agents phagey hands work to (rules of engagement, rule 8).
# Prints one line per problem and nothing when everyone is healthy:
#   DOWN <agent>     no live session
#   PROMPT <agent>   session is waiting at an interactive prompt (permission or confirmation)
# Exit status is 1 if any problem was found, 2 if the check itself failed (gt agents or
# gt peek erroring), with the reason on stderr. A failed check must never read as healthy.
#
# A parked or docked rig was shut down on purpose, so an agent that stays down there is
# expected. Crew sessions can outlive the parking, though, so an agent on such a rig that
# was live at the previous check and is now gone is still reported once.
set -uo pipefail

readonly DELEGATES=(monorepo/crew/gigi gs/crew/drummer ml/crew/lovelace dotfiles/crew/marsha data/crew/hopper)
# A live Claude Code confirmation renders its selected first option on a line of its own
# ("❯ 1. Yes") near the bottom of the pane. Anchoring to the line start keeps text that
# merely mentions the prompt, such as a script or a log, from matching.
readonly PROMPT_PATTERN='^[[:space:]]*❯ 1\. Yes'
# Agents that were live at the previous check, one per line.
readonly LIVE_STATE=${CHECK_DELEGATES_STATE:-"$HOME/.local/share/phagey-tools/delegates-live"}

cd ~/gt || exit 2
if ! live=$(timeout 60 gt agents 2>&1); then
  echo "gt agents failed: ${live:0:150}" >&2
  exit 2
fi
previously_live=$(cat "$LIVE_STATE" 2>/dev/null)
now_live=()
check_failures=()
problems=0

is_live() {
  local rig=$1 name=$2
  # `gt agents` groups sessions under "── <rig> ──" headings, one "  👷 crew/<name>" line
  # per session. Matching the whole last field keeps crew/gigi2 from passing for crew/gigi.
  awk -v rig="$rig" -v name="$name" '
      /^── / { in_rig = ($2 == rig) }
      in_rig && $NF == name { found = 1 }
      END { exit !found }' <<<"$live"
}

is_shut_down_on_purpose() {
  # Captured first: `grep -q` exiting early would SIGPIPE gt and fail the pipeline.
  local status
  status=$(timeout 30 gt rig status "$1" 2>/dev/null)
  grep -Eq 'Status: (PARKED|DOCKED)' <<<"$status"
}

for agent in "${DELEGATES[@]}"; do
  rig=${agent%%/*}
  name=${agent#*/}
  if ! is_live "$rig" "$name"; then
    if is_shut_down_on_purpose "$rig" && ! grep -Fxq "$agent" <<<"$previously_live"; then
      continue
    fi
    echo "DOWN $agent"
    problems=1
    continue
  fi
  now_live+=("$agent")
  if ! pane=$(timeout 60 gt peek "$agent" -n 25 2>&1); then
    check_failures+=("gt peek $agent failed: ${pane:0:150}")
    continue
  fi
  if tail -15 <<<"$pane" | grep -Eq "$PROMPT_PATTERN"; then
    echo "PROMPT $agent"
    problems=1
  fi
done

# The ${a[@]+...} form keeps macOS bash 3.2 from treating an empty array as unbound.
printf '%s\n' ${now_live[@]+"${now_live[@]}"} >"$LIVE_STATE"
if ((${#check_failures[@]} > 0)); then
  printf '%s\n' "${check_failures[@]}" >&2
  exit 2
fi
exit "$problems"
