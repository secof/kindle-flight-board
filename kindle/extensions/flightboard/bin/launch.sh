#!/bin/sh
# ==============================================================================
# KUAL Launcher Script for Kindle Flight Board
# ==============================================================================

PID_FILE="/tmp/flightboard.pid"
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
DAEMON_SCRIPT="${BIN_DIR}/update_board.sh"

action="${1:-start}"

case "$action" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "Daemon is already running."
            exit 0
        fi
        echo "Starting Flight Board Daemon in background..."
        nohup sh "$DAEMON_SCRIPT" loop > /dev/null 2>&1 &
        echo $! > "$PID_FILE"
        echo "Started daemon PID: $(cat "$PID_FILE")"
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            echo "Stopping Flight Board Daemon (PID: $PID)..."
            kill "$PID" 2>/dev/null
            rm -f "$PID_FILE"
            # Re-enable standard screen saver
            lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
            # Return to Kindle Home Screen booklet
            lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home 2>/dev/null
        else
            echo "Daemon is not running."
        fi
        ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "Daemon is running (PID: $(cat "$PID_FILE"))."
        else
            echo "Daemon is stopped."
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac
