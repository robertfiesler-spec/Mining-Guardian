#!/bin/sh
# query.sh — guardian-db skill wrapper
#
# Calls the Mining Guardian dashboard-api /query/* endpoints and prints
# the JSON response to stdout. The OpenClaw agent (Qwen) runs this script
# with a command name and optional arguments, reads the JSON, and
# summarizes the result for the user in Slack.
#
# TEMP: VPS-specific base URL. On May 1 2026 when Mining Guardian and
# OpenClaw are in the same docker-compose stack on a Mac mini, change
# GUARDIAN_API_URL to "http://mining-guardian:8585" (service-name DNS
# inside the compose network). That is a one-line change here.

# Default base URL — the Docker bridge gateway address that resolves
# to the VPS host from inside the OpenClaw container.
: "${GUARDIAN_API_URL:=http://172.18.0.1:8585}"

# curl flags:
#   -s        silent (no progress meter)
#   -S        but still show errors
#   --max-time 10  hard cap at 10 seconds so the skill never hangs Qwen
#   -f        fail on HTTP error status, but we capture body separately
CURL="curl -sS --max-time 10"

cmd="$1"
shift 2>/dev/null || true

if [ -z "$cmd" ]; then
    cat <<EOF
{"error": "no command specified. valid commands: fleet_summary, flagged_miners, miner_history, miner_outcomes, board_health, recent_actions, worst_performers, known_dead_boards, hvac_latest"}
EOF
    exit 1
fi

case "$cmd" in
    fleet_summary|flagged_miners|known_dead_boards|hvac_latest)
        # No arguments — simple GET
        $CURL "$GUARDIAN_API_URL/query/$cmd"
        ;;
    worst_performers)
        # Optional limit argument
        limit="${1:-5}"
        $CURL "$GUARDIAN_API_URL/query/worst_performers?limit=$limit"
        ;;
    recent_actions)
        # Optional hours and limit
        hours="${1:-4}"
        limit="${2:-50}"
        $CURL "$GUARDIAN_API_URL/query/recent_actions?hours=$hours&limit=$limit"
        ;;
    miner_history)
        # Required IP, optional hours
        ip="$1"
        hours="${2:-24}"
        if [ -z "$ip" ]; then
            echo '{"error": "miner_history requires an IP argument. Example: query.sh miner_history 192.168.188.36"}'
            exit 1
        fi
        $CURL "$GUARDIAN_API_URL/query/miner_history/$ip?hours=$hours"
        ;;
    miner_outcomes)
        # Required IP, optional limit
        ip="$1"
        limit="${2:-20}"
        if [ -z "$ip" ]; then
            echo '{"error": "miner_outcomes requires an IP argument. Example: query.sh miner_outcomes 192.168.188.36"}'
            exit 1
        fi
        $CURL "$GUARDIAN_API_URL/query/miner_outcomes/$ip?limit=$limit"
        ;;
    board_health)
        # Required IP
        ip="$1"
        if [ -z "$ip" ]; then
            echo '{"error": "board_health requires an IP argument. Example: query.sh board_health 192.168.188.36"}'
            exit 1
        fi
        $CURL "$GUARDIAN_API_URL/query/board_health/$ip"
        ;;
    *)
        cat <<EOF
{"error": "unknown command: $cmd. valid commands: fleet_summary, flagged_miners, miner_history, miner_outcomes, board_health, recent_actions, worst_performers, known_dead_boards, hvac_latest"}
EOF
        exit 1
        ;;
esac
