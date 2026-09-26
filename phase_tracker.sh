#!/bin/bash
# Phase tracking tool for on-call voice agent
# Phases: talking, execute, verified, failed, drop

PHASE=$1
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

if [ -z "$PHASE" ]; then
    echo "Usage: $0 <talking|execute|verified|failed|drop>"
    exit 1
fi

case $PHASE in
    talking|execute|verified|failed|drop)
        echo "[$TIMESTAMP] Phase: $PHASE" | tee -a /workspace/incident_log.txt
        ;;
    *)
        echo "Invalid phase. Use: talking, execute, verified, failed, or drop"
        exit 1
        ;;
esac
