#!/bin/bash
#
# S21 Immersion Firmware Benchmark — Test Runner
# ===============================================
# Runs the full 60-hour benchmark test across 4 phases.
#
# Usage:
#   ./run_benchmark.sh start      # Start from Phase 1, Hour 0
#   ./run_benchmark.sh resume 2 5 # Resume from Phase 2, Hour 5
#   ./run_benchmark.sh collect 1 0 # Single collection (Phase 1, Hour 0)
#
# Test Schedule:
#   Phase 1: Stock       — 24 hours (hours 0-23)
#   Phase 2: +10% OC     — 12 hours (hours 0-11)
#   Phase 3: +25% OC     — 12 hours (hours 0-11)
#   Phase 4: Max OC      — 12 hours (hours 0-11)
#
# Total: 60 hours of data collection
#
# IMPORTANT: You must manually change the power profile on the miners
# at the start of each phase. The script will remind you.
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COLLECTOR="$SCRIPT_DIR/s21_benchmark_collector.py"
VENV="$SCRIPT_DIR/../venv"
LOG_FILE="$SCRIPT_DIR/benchmark.log"

# Activate venv
source "$VENV/bin/activate"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

notify_slack() {
    # Optional: Send Slack notification
    # curl -X POST -H 'Content-type: application/json' \
    #   --data "{\"text\":\"$1\"}" \
    #   "$SLACK_WEBHOOK_URL"
    log "NOTIFICATION: $1"
}

collect_hour() {
    local phase=$1
    local hour=$2
    log "Collecting Phase $phase, Hour $hour..."
    python3 "$COLLECTOR" --phase "$phase" --hour "$hour" 2>&1 | tee -a "$LOG_FILE"
}

run_phase() {
    local phase=$1
    local start_hour=$2
    local total_hours=$3
    local phase_name=$4
    
    log "=========================================="
    log "PHASE $phase: $phase_name"
    log "Duration: $total_hours hours"
    log "=========================================="
    
    notify_slack "🔬 S21 Benchmark: Starting Phase $phase ($phase_name)"
    
    for hour in $(seq "$start_hour" $((total_hours - 1))); do
        collect_hour "$phase" "$hour"
        
        if [ "$hour" -lt $((total_hours - 1)) ]; then
            log "Sleeping 1 hour until next collection..."
            sleep 3600
        fi
    done
    
    notify_slack "✅ S21 Benchmark: Phase $phase ($phase_name) complete!"
}

prompt_profile_change() {
    local phase=$1
    local profile=$2
    
    echo ""
    echo "============================================"
    echo "⚠️  ACTION REQUIRED: Change power profile!"
    echo "============================================"
    echo "Phase $phase requires: $profile"
    echo ""
    echo "Go to AMS and set both S21 Imm miners to:"
    echo "  - 192.168.188.22"
    echo "  - 192.168.188.23"
    echo ""
    echo "Press ENTER when profile change is complete..."
    read -r
    echo "Waiting 5 minutes for miners to stabilize..."
    sleep 300
}

case "$1" in
    start)
        log "Starting S21 Immersion Firmware Benchmark Test"
        log "Total duration: ~60 hours"
        
        # Phase 1: Stock (24 hours)
        prompt_profile_change 1 "STOCK (default profile)"
        run_phase 1 0 24 "Stock"
        
        # Phase 2: +10% OC (12 hours)
        prompt_profile_change 2 "+10% OVERCLOCK"
        run_phase 2 0 12 "+10% OC"
        
        # Phase 3: +25% OC (12 hours)
        prompt_profile_change 3 "+25% OVERCLOCK"
        run_phase 3 0 12 "+25% OC"
        
        # Phase 4: Max OC (12 hours)
        prompt_profile_change 4 "MAXIMUM OVERCLOCK"
        run_phase 4 0 12 "Max OC"
        
        log "=========================================="
        log "BENCHMARK COMPLETE!"
        log "Data saved to: $SCRIPT_DIR/s21_imm_benchmark.csv"
        log "=========================================="
        notify_slack "🎉 S21 Benchmark COMPLETE! 60 hours of data collected."
        ;;

    resume)
        if [ -z "$2" ] || [ -z "$3" ]; then
            echo "Usage: $0 resume <phase> <hour>"
            exit 1
        fi
        phase=$2
        hour=$3
        
        log "Resuming from Phase $phase, Hour $hour"
        
        case "$phase" in
            1)
                run_phase 1 "$hour" 24 "Stock"
                prompt_profile_change 2 "+10% OVERCLOCK"
                run_phase 2 0 12 "+10% OC"
                prompt_profile_change 3 "+25% OVERCLOCK"
                run_phase 3 0 12 "+25% OC"
                prompt_profile_change 4 "MAXIMUM OVERCLOCK"
                run_phase 4 0 12 "Max OC"
                ;;
            2)
                run_phase 2 "$hour" 12 "+10% OC"
                prompt_profile_change 3 "+25% OVERCLOCK"
                run_phase 3 0 12 "+25% OC"
                prompt_profile_change 4 "MAXIMUM OVERCLOCK"
                run_phase 4 0 12 "Max OC"
                ;;
            3)
                run_phase 3 "$hour" 12 "+25% OC"
                prompt_profile_change 4 "MAXIMUM OVERCLOCK"
                run_phase 4 0 12 "Max OC"
                ;;
            4)
                run_phase 4 "$hour" 12 "Max OC"
                ;;
            *)
                echo "Invalid phase: $phase (must be 1-4)"
                exit 1
                ;;
        esac
        
        log "BENCHMARK COMPLETE!"
        notify_slack "🎉 S21 Benchmark COMPLETE!"
        ;;
    
    collect)
        if [ -z "$2" ] || [ -z "$3" ]; then
            echo "Usage: $0 collect <phase> <hour>"
            exit 1
        fi
        collect_hour "$2" "$3"
        ;;
    
    test)
        log "Running test collection (Phase 1, Hour 0)..."
        collect_hour 1 0
        ;;
    
    *)
        echo "S21 Immersion Firmware Benchmark Test Runner"
        echo ""
        echo "Usage:"
        echo "  $0 start              Start full 60-hour benchmark"
        echo "  $0 resume <phase> <hour>  Resume from specific point"
        echo "  $0 collect <phase> <hour> Single collection"
        echo "  $0 test               Test single collection"
        echo ""
        echo "Phases:"
        echo "  1: Stock (24 hours)"
        echo "  2: +10% OC (12 hours)"
        echo "  3: +25% OC (12 hours)"
        echo "  4: Max OC (12 hours)"
        exit 1
        ;;
esac
