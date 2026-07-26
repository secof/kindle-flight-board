#!/bin/sh
# ==============================================================================
# Kindle Flight Board Update Daemon (Firmware 5.17 / Winterbreak)
# ==============================================================================

# DEFAULT CONFIGURATION - CAN BE OVERRIDDEN BY config.env OR /mnt/us/flightboard.conf
SERVER_URL="http://192.168.1.100:8000"
POLL_INTERVAL=60           # Seconds between polling checks
TOGGLE_WIFI=0             # Set to 1 to disable Wi-Fi between updates for maximum battery
ROTATE=90                 # 90 or 270 degrees rotation for landscape view on Kindle e-ink
LOG_FILE="/tmp/flightboard.log"
HASH_FILE="/tmp/flightboard_last_hash.txt"
IMAGE_FILE="/tmp/flightboard_board.png"
TEMP_IMAGE_FILE="/tmp/flightboard_download.tmp.png"
MODE="${1:-loop}"         # 'loop' or 'once'

# LOAD USER CONFIGURATION FILE IF PRESENT
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$EXT_DIR/config.env" ]; then
    . "$EXT_DIR/config.env"
elif [ -f "/mnt/us/flightboard.conf" ]; then
    . "/mnt/us/flightboard.conf"
fi

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Locate Kindle system binaries for FW 5.17 / Winterbreak (armhf)
if [ -x /usr/bin/eips ]; then
    EIPS_CMD="/usr/bin/eips"
else
    EIPS_CMD="eips"
fi

if [ -x /usr/bin/lipc-set-prop ]; then
    LIPC_CMD="/usr/bin/lipc-set-prop"
else
    LIPC_CMD="lipc-set-prop"
fi

init_kindle_environment() {
    log "Initializing Kindle FW 5.17 (Winterbreak) environment..."
    # Prevent Kindle powerd from auto-sleeping / going to screensaver
    $LIPC_CMD com.lab126.powerd preventScreenSaver 1 2>/dev/null
}

enable_wifi() {
    if [ "$TOGGLE_WIFI" -eq 1 ]; then
        log "Enabling Wi-Fi..."
        $LIPC_CMD com.lab126.cmd wirelessEnable 1 2>/dev/null
        sleep 5
    fi
}

disable_wifi() {
    if [ "$TOGGLE_WIFI" -eq 1 ]; then
        log "Disabling Wi-Fi to conserve battery..."
        $LIPC_CMD com.lab126.cmd wirelessEnable 0 2>/dev/null
    fi
}

display_error() {
    curl_err="$1"
    url_target="$2"
    log "Displaying on-screen connection error (code $curl_err)..."
    
    $EIPS_CMD -f -c 2>/dev/null
    sleep 1
    $EIPS_CMD 2 2 "=== KINDLE FLIGHT BOARD ERROR ===" 2>/dev/null
    $EIPS_CMD 2 4 "Failed to connect to backend server!" 2>/dev/null
    $EIPS_CMD 2 6 "URL: $url_target" 2>/dev/null
    $EIPS_CMD 2 8 "curl exit code: $curl_err" 2>/dev/null
    $EIPS_CMD 2 10 "Please check SERVER_URL in config.env" 2>/dev/null
    $EIPS_CMD 2 12 "e.g. SERVER_URL=\"http://<UNRAID_IP>:8000\"" 2>/dev/null
}

display_image() {
    log "Updating e-ink display with new board image ($IMAGE_FILE)..."
    
    # Open Kindle blank app canvas to remove 'From your library' home screen cleanly
    $LIPC_CMD com.lab126.appmgrd start app://com.lab126.blank 2>/dev/null
    sleep 1

    # Keep screensaver disabled
    $LIPC_CMD com.lab126.powerd preventScreenSaver 1 2>/dev/null

    # Hardware full-screen refresh to clear all layers and eliminate ghosting / bleeding
    $EIPS_CMD -f -c 2>/dev/null
    sleep 1
    # Render PNG image onto full Kindle display
    $EIPS_CMD -f -g "$IMAGE_FILE" 2>/dev/null
}

compute_hash() {
    file_path="$1"
    if command -v md5sum >/dev/null 2>&1; then
        md5sum "$file_path" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file_path" | awk '{print $1}'
    else
        ls -l "$file_path" | awk '{print $5}'
    fi
}

update_cycle() {
    enable_wifi

    BOARD_URL="${SERVER_URL}/board.png?rotate=${ROTATE}"
    CHANGED_URL="${SERVER_URL}/changed"

    LAST_HASH=""
    if [ -f "$HASH_FILE" ]; then
        LAST_HASH=$(cat "$HASH_FILE")
    fi

    NEED_DOWNLOAD=1

    # 1. Check lightweight /changed status endpoint if hash exists
    if [ -n "$LAST_HASH" ]; then
        log "Checking status endpoint: ${CHANGED_URL}?hash=${LAST_HASH}"
        RESPONSE=$(curl -s --max-time 10 "${CHANGED_URL}?hash=${LAST_HASH}" 2>/dev/null)
        CURL_STATUS=$?

        if [ $CURL_STATUS -eq 0 ] && [ -n "$RESPONSE" ]; then
            IS_CHANGED=$(echo "$RESPONSE" | grep -o '"changed":true')
            if [ -z "$IS_CHANGED" ] && [ -f "$IMAGE_FILE" ]; then
                log "Server reports board data unchanged. Skipping download & e-ink refresh."
                NEED_DOWNLOAD=0
            fi
        fi
    fi

    # 2. Fetch /board.png if data changed or first run
    if [ "$NEED_DOWNLOAD" -eq 1 ] || [ ! -f "$IMAGE_FILE" ]; then
        log "Downloading board image from: $BOARD_URL"
        curl -s --max-time 15 -o "$TEMP_IMAGE_FILE" "$BOARD_URL" 2>/dev/null
        CURL_STATUS=$?

        if [ $CURL_STATUS -eq 0 ] && [ -s "$TEMP_IMAGE_FILE" ]; then
            NEW_HASH=$(compute_hash "$TEMP_IMAGE_FILE")

            if [ "$NEW_HASH" != "$LAST_HASH" ] || [ ! -f "$IMAGE_FILE" ]; then
                mv "$TEMP_IMAGE_FILE" "$IMAGE_FILE"
                display_image
                echo "$NEW_HASH" > "$HASH_FILE"
                log "Successfully updated board image (Hash: $NEW_HASH)."
            else
                log "Downloaded board image is identical to active display. Skipping e-ink redraw."
                rm -f "$TEMP_IMAGE_FILE"
            fi
        else
            log "ERROR: Download from $BOARD_URL failed or returned empty image (curl code: $CURL_STATUS)."
            rm -f "$TEMP_IMAGE_FILE"
            display_error "$CURL_STATUS" "$BOARD_URL"
            disable_wifi
            return 1
        fi
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
