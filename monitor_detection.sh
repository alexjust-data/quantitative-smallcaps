#!/bin/bash
# Monitor script for intraday event detection
# Usage: bash monitor_detection.sh

echo "=========================================="
echo "INTRADAY EVENT DETECTION MONITOR"
echo "=========================================="
echo ""

# Find latest log file
LATEST_LOG=$(ls -t D:/04_TRADING_SMALLCAPS/logs/detect_events/run_full_*.log 2>/dev/null | head -1)

if [ -z "$LATEST_LOG" ]; then
    echo "No log file found!"
    exit 1
fi

echo "Monitoring: $LATEST_LOG"
echo ""

# Check if process is running
PROCESS_COUNT=$(ps aux | grep "detect_events_intraday.py" | grep -v grep | wc -l)
if [ $PROCESS_COUNT -gt 0 ]; then
    echo "✅ Process is RUNNING"
else
    echo "❌ Process is NOT running"
fi
echo ""

# Show recent progress
echo "Last 10 log entries:"
echo "----------------------------------------"
tail -10 "$LATEST_LOG" | sed 's/\x1b\[[0-9;]*m//g'
echo ""

# Check checkpoint
CHECKPOINT=$(ls -t D:/04_TRADING_SMALLCAPS/logs/checkpoints/events_intraday_*_completed.json 2>/dev/null | head -1)
if [ -n "$CHECKPOINT" ]; then
    echo "Checkpoint status:"
    echo "----------------------------------------"
    cat "$CHECKPOINT" | python -m json.tool 2>/dev/null | grep -E '"total_completed"|"last_updated"'
    echo ""
fi

# Check heartbeat
HEARTBEAT=$(ls -t D:/04_TRADING_SMALLCAPS/logs/heartbeats/events_intraday_*_heartbeat.json 2>/dev/null | head -1)
if [ -n "$HEARTBEAT" ]; then
    echo "Heartbeat (last activity):"
    echo "----------------------------------------"
    cat "$HEARTBEAT" | python -m json.tool 2>/dev/null
    echo ""
fi

# Count shards
SHARD_COUNT=$(ls D:/04_TRADING_SMALLCAPS/processed/events/shards/events_intraday_*_shard*.parquet 2>/dev/null | wc -l)
echo "Shards saved: $SHARD_COUNT"
echo ""

echo "To watch live:"
echo "  tail -f $LATEST_LOG"
echo ""
echo "To check process:"
echo "  ps aux | grep detect_events_intraday.py"
