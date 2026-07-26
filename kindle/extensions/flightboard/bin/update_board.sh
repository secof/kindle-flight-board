#!/bin/sh
# ==============================================================================
# Kindle Flight Board Update Daemon (Firmware 5.17 / Winterbreak)
# ==============================================================================

# CONFIGURATION - CHANGE THIS TO YOUR UNRAID SERVER IP
SERVER_URL="http://192.168.1.100:8000"
POLL_INTERVAL=60           # Seconds between polling checks
TOGGLE_WIFI=0             # Set to 1 to disable Wi-Fi between updates for maximum battery
LOG_FILE="/tmp/flightboard.log"
HASH_FILE="/tmp/flightboard_last_hash.txt"
IMAGE_FILE="/tmp/flightboard_board.png"
MODE="${1:-loop}"         # 'loop' or 'once'

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

init_kindle_environment() {
    log "Initializing Kindle FW 5.17 environment..."
    # Prevent Kindle from auto-sleeping / going to lock screen
    lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
    
    # Ensure frameworks don't interrupt display
    if [ -x /usr/bin/eips ]; then
        EIPS_CMD="/usr/bin/eips"
    else
        EIPS_CMD="eips"
    fi
}

enable_wifi() {
    if [ "$TOGGLE_WIFI" -eq 1 ]; then
        log "Enabling Wi-Fi..."
        lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null
        sleep 5
    fi
}

disable_wifi() {
    if [ "$TOGGLE_WIFI" -eq 1 ]; then
        log "Disabling Wi-Fi to conserve battery..."
        lipc-set-prop com.lab126.cmd wirelessEnable 0 2>/dev/null
    fi
}

display_image() {
    log "Updating e-ink display with new board image..."
    # Clear screen to flash black/white and eliminate e-ink ghosting (FW 5.17)
    $EIPS_CMD -c 2>/dev/null
    sleep 1
    # Render PNG image onto screen
    $EIPS_CMD -g "$IMAGE_FILE" 2>/dev/null
}

update_cycle() {
    enable_wifi

    LAST_HASH=""
    if [ -f "$HASH_FILE" ]; then
        LAST_HASH=$(cat "$HASH_FILE")
    fi

    # Query /changed endpoint
    CHANGED_URL="${SERVER_URL}/changed?hash=${LAST_HASH}"
    log "Checking endpoint: $CHANGED_URL"

    RESPONSE=$(curl -s --max-time 10 "$CHANGED_URL" 2>/dev/null)
    CURL_STATUS=$?

    if [ $CURL_STATUS -ne 0 ] || [ -z "$RESPONSE" ]; then
        log "ERROR: Failed to connect to server (curl exit code $CURL_STATUS)."
        disable_wifi
        return 1
    fi

    IS_CHANGED=$(echo "$RESPONSE" | grep -o '"changed":true')
    NEW_HASH=$(echo "$RESPONSE" | grep -o '"data_hash":"[^"]*"' | cut -d'"' -f4)

    if [ -n "$IS_CHANGED" ] || [ ! -f "$IMAGE_FILE" ]; then
        log "Data changed or image missing (Hash: $NEW_HASH). Downloading new board..."
        
        BOARD_URL="${SERVER_URL}/board.png"
        curl -s --max-time 15 -o "$IMAGE_FILE" "$BOARD_URL" 2>/dev/null
        
        if [ $? -eq 0 ] && [ -s "$IMAGE_FILE" ]; then
            display_image
            echo "$NEW_HASH" > "$HASH_FILE"
            log "Successfully updated board image."
        else
            log "ERROR: Downloaded board.png was empty or failed."
        fi
    else
        log "Board data unchanged. Skipping refresh."
    fi

    disable_wifi
    return 0
}

# MAIN EXECUTION
init_kindle_environment

if [ "$MODE" = "once" ]; then
    log "Running single update cycle..."
    update_cycle
    exit $?
fi

log "Starting Kindle Flight Board continuous daemon (Interval: ${POLL_INTERVAL}s)..."

while true; do
    update_cycle
    sleep "$POLL_INTERVAL"
done
