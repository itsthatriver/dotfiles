#!/usr/bin/env bash
# ollama-mempressure.sh — Quick memory pressure snapshot for the currently-loaded Ollama model.
#
# Usage:
#   ./ollama-mempressure.sh                          # snapshot whatever's loaded
#   ./ollama-mempressure.sh qwen3.6:35b-a3b          # load this model first, then snapshot
#   ./ollama-mempressure.sh qwen3.6:35b-a3b 32768    # load with custom context
#   ./ollama-mempressure.sh --watch                  # refresh every 3s
#
# Reports: model footprint, system memory breakdown, swap activity delta,
# compression ratio, and a verdict on whether the system is healthy.

set -uo pipefail

WATCH=0
MODEL=""
CONTEXT=""

# ── Parse args ───────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --watch|-w) WATCH=1 ;;
        --help|-h)
            sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *)
            if [ -z "$MODEL" ]; then MODEL="$arg"
            elif [ -z "$CONTEXT" ]; then CONTEXT="$arg"
            fi ;;
    esac
done

PAGE_SIZE=$(pagesize)
TOTAL_BYTES=$(sysctl -n hw.memsize)
TOTAL_GB=$(echo "scale=1; $TOTAL_BYTES / 1024 / 1024 / 1024" | bc)

# Color output if stdout is a tty
if [ -t 1 ]; then
    RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'
    DIM=$'\033[2m';  BLD=$'\033[1m';  RST=$'\033[0m'
else
    RED=""; YEL=""; GRN=""; DIM=""; BLD=""; RST=""
fi

# ── Helpers ──────────────────────────────────────────────────────────
gb()      { echo "scale=1; $1 / 1024 / 1024 / 1024" | bc; }
pages_gb() { echo "scale=1; $1 * $PAGE_SIZE / 1024 / 1024 / 1024" | bc; }
pct()     { echo "scale=0; $1 * 100 / $2" | bc; }

color_for_pct() {
    local p=$1
    if   [ "$p" -ge 90 ]; then echo "$RED"
    elif [ "$p" -ge 75 ]; then echo "$YEL"
    else                       echo "$GRN"; fi
}

# ── Load model if specified ─────────────────────────────────────────
if [ -n "$MODEL" ]; then
    echo "${DIM}Loading $MODEL${CONTEXT:+ with context=$CONTEXT}...${RST}"
    if [ -n "$CONTEXT" ]; then
        OLLAMA_CONTEXT_LENGTH="$CONTEXT" ollama run "$MODEL" "ok" >/dev/null 2>&1
    else
        ollama run "$MODEL" "ok" >/dev/null 2>&1
    fi
    sleep 1
fi

# ── Snapshot function ───────────────────────────────────────────────
snapshot() {
    local ts; ts=$(date +%H:%M:%S)
    echo
    echo "${BLD}═══ Memory snapshot at $ts ═══${RST}  total: ${TOTAL_GB} GB"
    echo

    # ── Loaded model ────────────────────────────────────────────────
    local ps_out
    ps_out=$(ollama ps 2>/dev/null | tail -n +2)
    if [ -z "$ps_out" ]; then
        echo "${DIM}No model currently loaded${RST}"
    else
        echo "${BLD}Loaded model${RST}"
        echo "$ps_out" | while read -r line; do
            local name size ctx
            name=$(echo "$line" | awk '{print $1}')
            size=$(echo "$line" | awk '{print $3, $4}')
            ctx=$(echo "$line"  | awk '{print $6}')
            printf "  %-32s  %10s   ctx=%s\n" "$name" "$size" "$ctx"
        done

        # Get actual physical footprint of runner process
        local runner_pid footprint_gb
        runner_pid=$(pgrep -f "ollama runner" | head -1)
        if [ -n "$runner_pid" ]; then
            footprint_gb=$(footprint "$runner_pid" 2>/dev/null \
                | awk '/phys_footprint:/ {print $2, $3; exit}')
            [ -n "$footprint_gb" ] && \
                printf "  ${DIM}runner phys_footprint: %s${RST}\n" "$footprint_gb"
        fi
    fi
    echo

    # ── System memory breakdown ────────────────────────────────────
    local vm_out
    vm_out=$(vm_stat)
    local free        active inactive wired compressed speculative
    free=$(       echo "$vm_out" | awk '/Pages free/                   {gsub(/\./,""); print $3}')
    active=$(     echo "$vm_out" | awk '/Pages active/                 {gsub(/\./,""); print $3}')
    inactive=$(   echo "$vm_out" | awk '/Pages inactive/               {gsub(/\./,""); print $3}')
    wired=$(      echo "$vm_out" | awk '/Pages wired down/             {gsub(/\./,""); print $4}')
    compressed=$( echo "$vm_out" | awk '/Pages occupied by compressor/ {gsub(/\./,""); print $5}')
    speculative=$(echo "$vm_out" | awk '/Pages speculative/            {gsub(/\./,""); print $3}')

    local free_gb active_gb inactive_gb wired_gb compressed_gb
    free_gb=$(pages_gb       "${free:-0}")
    active_gb=$(pages_gb     "${active:-0}")
    inactive_gb=$(pages_gb   "${inactive:-0}")
    wired_gb=$(pages_gb      "${wired:-0}")
    compressed_gb=$(pages_gb "${compressed:-0}")

    # Truly available = free + speculative + inactive (reclaimable)
    local avail_pages avail_gb avail_pct avail_color
    avail_pages=$(( ${free:-0} + ${speculative:-0} + ${inactive:-0} ))
    avail_gb=$(pages_gb "$avail_pages")
    avail_pct=$(pct "$avail_pages" "$(( TOTAL_BYTES / PAGE_SIZE ))")
    avail_color=$(color_for_pct $((100 - avail_pct)))

    # Used (non-reclaimable) = active + wired + compressed
    local used_pages used_gb used_pct
    used_pages=$(( ${active:-0} + ${wired:-0} + ${compressed:-0} ))
    used_gb=$(pages_gb "$used_pages")
    used_pct=$(pct "$used_pages" "$(( TOTAL_BYTES / PAGE_SIZE ))")
    local used_color; used_color=$(color_for_pct "$used_pct")

    echo "${BLD}System memory${RST}"
    printf "  free:        %6s GB\n" "$free_gb"
    printf "  active:      %6s GB  ${DIM}(in use)${RST}\n" "$active_gb"
    printf "  wired:       %6s GB  ${DIM}(kernel/pinned)${RST}\n" "$wired_gb"
    printf "  inactive:    %6s GB  ${DIM}(reclaimable)${RST}\n" "$inactive_gb"
    printf "  compressed:  %6s GB  ${DIM}(memory under pressure)${RST}\n" "$compressed_gb"
    echo
    printf "  ${used_color}committed:   %6s GB  (%s%% of total)${RST}\n" "$used_gb" "$used_pct"
    printf "  ${avail_color}available:   %6s GB  (%s%% of total)${RST}\n" "$avail_gb" "$avail_pct"
    echo

    # ── Swap activity ──────────────────────────────────────────────
    local swap_out
    swap_out=$(sysctl -n vm.swapusage 2>/dev/null)
    if [ -n "$swap_out" ]; then
        echo "${BLD}Swap${RST}"
        printf "  ${DIM}%s${RST}\n" "$swap_out"

        # Delta swap I/O if we have a previous reading
        local sin sout
        sin=$( sysctl -n vm.pageins  2>/dev/null || echo 0)
        sout=$(sysctl -n vm.pageouts 2>/dev/null || echo 0)
        local state_file=/tmp/.ollama-mempressure-$USER
        if [ -f "$state_file" ]; then
            local prev_sin prev_sout prev_ts
            read -r prev_sin prev_sout prev_ts < "$state_file"
            local delta_sin delta_sout delta_t
            delta_sin=$((  sin  - prev_sin  ))
            delta_sout=$(( sout - prev_sout ))
            delta_t=$((    $(date +%s) - prev_ts ))
            if [ "$delta_t" -gt 0 ]; then
                printf "  pageouts since last run:  %s ${DIM}(%ss ago)${RST}\n" \
                    "$delta_sout" "$delta_t"
                if [ "$delta_sout" -gt 10000 ]; then
                    echo "  ${RED}↑ heavy paging — system is swapping to disk${RST}"
                elif [ "$delta_sout" -gt 1000 ]; then
                    echo "  ${YEL}↑ moderate paging${RST}"
                fi
            fi
        fi
        echo "$sin $sout $(date +%s)" > "$state_file"
    fi
    echo

    # ── Compression ratio ──────────────────────────────────────────
    if [ "${compressed:-0}" -gt 0 ]; then
        local decomp_pages comp_pages
        decomp_pages=$(echo "$vm_out" \
            | awk '/Pages decompressed/ {gsub(/\./,""); print $3}')
        comp_pages=$(  echo "$vm_out" \
            | awk '/Pages compressed/   {gsub(/\./,""); print $3}')
        if [ -n "$decomp_pages" ] && [ "$decomp_pages" -gt 0 ]; then
            local ratio
            ratio=$(echo "scale=2; $decomp_pages / $comp_pages" | bc)
            printf "${DIM}  compressor: %s pages held, lifetime decomp/comp ratio %s${RST}\n" \
                "$compressed" "$ratio"
        fi
    fi

    # ── Verdict ────────────────────────────────────────────────────
    echo
    if [ "$used_pct" -ge 90 ]; then
        echo "${RED}${BLD}VERDICT: critical — actively swapping, model is too big${RST}"
    elif [ "$used_pct" -ge 80 ]; then
        echo "${YEL}${BLD}VERDICT: tight — model fits but no headroom for spikes${RST}"
    elif [ "$used_pct" -ge 65 ]; then
        echo "${GRN}${BLD}VERDICT: workable — reasonable headroom${RST}"
    else
        echo "${GRN}${BLD}VERDICT: comfortable — plenty of room${RST}"
    fi
}

# ── Main ────────────────────────────────────────────────────────────
if [ "$WATCH" -eq 1 ]; then
    while true; do
        clear
        snapshot
        sleep 3
    done
else
    snapshot
fi