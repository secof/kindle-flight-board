# Kindle Flight Board ✈️📺

A smart-display system that turns a jailbroken **Amazon Kindle Paperwhite** into a live flight departures/arrivals board for any airport using the **Flightradar24 API** and a local **Unraid / Docker** backend.

---

## 🌟 Key Features

- **Kindle FW 5.17 & Winterbreak Ready:** Integrated blank canvas (`app://com.lab126.blank`) and Java UI background pausing (`killall -STOP cvm`) to permanently prevent *"From your library"* from repainting over your flight board.
- **Flightradar24 API Integration:** Fetches live airport departure and arrival schedules sorted by real-time operational timestamps (`effective_ts`), properly handling delayed and early flights without premature drop-offs.
- **Battery-Optimized Polling:** The Kindle checks a lightweight `/changed` hash endpoint before downloading new images, avoiding unnecessary Wi-Fi & e-ink redraw power draw.
- **102+ Airline Logos & Alias Resolution:** Includes 102 airline logos with automatic IATA/ICAO/subsidiary alias lookups (`W6`/`W4`/`WZZ` for Wizz Air, `FR`/`RK`/`RYR` for Ryanair, `RO`/`ROT` for TAROM, etc.).
- **Custom Plane Graphics:** Uses high-contrast `departure.png` and `landing.png` vector plane icons positioned to the left of airline logos.
- **Clear 3-Line Destination Layout:** Displays Airport Code (e.g. `BGY`), City Name (e.g. `Milan Bergamo`), and Aircraft Model (e.g. `A321`).
- **Centered 2-Row Status Column:** Displays `EST` / `DLY` on top and the status time on the bottom line, centered horizontally.
- **Pure White High-Contrast E-Ink Rendering:** Built with Python Pillow (PIL) and bundled TrueType fonts ([Arial.ttf](assets/fonts/Arial.ttf)) for maximum e-ink legibility and 100% pure white background (`fill=255`).
- **Unraid & Docker Ready:** Published to GitHub Container Registry (`ghcr.io/secof/kindle-flight-board:latest`) with automatic `/app/assets` volume population so custom logos & fonts can be mounted seamlessly.

---

## 📐 Architecture Overview

```mermaid
graph TD
    A[Flightradar24 API] -->|JSON Flight Data| B[Backend Server - FastAPI]
    B -->|Render 800x600 PNG| C[Pillow Graphics Engine]
    C -->|Expose Endpoints| D[Local Network: /changed & /board.png]
    
    subgraph Kindle Paperwhite (FW 5.17 / Winterbreak)
        E[KUAL Menu / Launch Script] -->|Poll /changed| D
        D -->|If Hash Changed| F[Download /board.png]
        F -->|Clear & Draw eips -f -c -g| G[E-Ink Screen Update]
    end
```

---

## 📂 Monorepo Structure

```
kindle-flight-board/
├── assets/
│   ├── fonts/               # TrueType fonts (Arial.ttf)
│   ├── logos/               # 102+ Airline logo PNGs & aliases.json
│   ├── plane/               # departure.png and landing.png icons
│   └── sample_board.png
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py        # Settings via Pydantic & environment variables
│   │   ├── flight_service.py # Flightradar24 API client & caching
│   │   ├── main.py          # FastAPI application & endpoints
│   │   ├── models.py        # Pydantic data schemas
│   │   └── renderer.py      # Pillow high-contrast e-ink renderer
│   ├── Dockerfile           # Multi-stage asset-protected Docker build
│   └── requirements.txt
├── kindle/
│   └── extensions/
│       └── flightboard/
│           ├── config.xml   # KUAL extension configuration
│           ├── menu.json    # KUAL button definitions
│           ├── config.env.example
│           └── bin/
│               ├── launch.sh        # Daemon background runner & cvm unfreeze
│               └── update_board.sh  # Main Kindle polling daemon script (cvm freeze)
├── docker-compose.yml       # Docker Compose setup
├── unraid-template.xml      # Unraid OS Docker XML template
└── README.md
```

---

## 🚀 Backend Deployment (Unraid / Docker)

### Option 1: Docker Compose

1. Clone repository to your server:
   ```bash
   git clone https://github.com/secof/kindle-flight-board.git
   cd kindle-flight-board
   ```
2. Edit `docker-compose.yml` to set your target `AIRPORT_ICAO` (e.g. `LRBS`, `BGY`, `LTN`, `KJFK`), timezone, and dimensions:
   ```yaml
   environment:
     - AIRPORT_ICAO=LRBS
     - AIRPORT_NAME=Aeroportul Internațional București Băneasa
     - TIMEZONE=Europe/Bucharest
     - BOARD_WIDTH=800
     - BOARD_HEIGHT=600
     - ROTATE_DEGREES=90
   ```
3. Start container:
   ```bash
   docker-compose up -d --build
   ```

### Option 2: Unraid OS Container
1. Copy `unraid-template.xml` into your Unraid server template folder:
   `/boot/config/plugins/dockerMan/templates-user/my-kindle-flight-board.xml`
2. Go to **Docker** $\rightarrow$ **Add Container** in Unraid web UI and select `kindle-flight-board`.
3. Set your target airport ICAO code (e.g., `LRBS`, `BGY`) and click **Apply**.

---

## 📟 Kindle Setup (Firmware 5.17 / Winterbreak)

### Requirements:
- Kindle Paperwhite running Firmware **5.17** with **Winterbreak** jailbreak installed.
- **KUAL** (Kindle Unified Application Launcher) installed.

### Installation Steps:
1. Connect your Kindle to your computer via USB.
2. Copy ONLY the `flightboard` folder from `kindle/extensions/flightboard/` on your computer into the `extensions/` directory on your Kindle USB drive.
   
   > [!IMPORTANT]
   > The path on your Kindle USB drive **MUST** be exactly:
   > `[Kindle USB Root]/extensions/flightboard/menu.json`

3. Set your server IP by editing `config.env` inside `[Kindle USB Drive]/extensions/flightboard/config.env`:
   ```sh
   SERVER_URL="http://192.168.1.100:8000"
   POLL_INTERVAL=60
   TOGGLE_WIFI=0
   ROTATE=90
   STOP_FRAMEWORK=1
   ```
4. Safely eject your Kindle USB drive.
5. Open **KUAL** on your Kindle, tap **Kindle Flight Board** $\rightarrow$ **Update Board Once** (or **Start Flight Board Daemon**).

---

## ⚙️ Configuration Reference

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `AIRPORT_ICAO` | `LRBS` | Target airport ICAO code (e.g. `LRBS`, `BGY`, `LTN`, `KJFK`) |
| `AIRPORT_NAME` | `Aeroportul Internațional București Băneasa` | Display title for airport header |
| `TIMEZONE` | `Europe/Bucharest` | Target timezone for departure/arrival timestamps |
| `BOARD_WIDTH` | `800` | Native Kindle display width in pixels |
| `BOARD_HEIGHT` | `600` | Native Kindle display height in pixels |
| `ROTATE_DEGREES` | `90` | Image rotation (0, 90, 180, 270) |
| `INVERT_COLORS` | `false` | Invert black/white for dark mode e-ink display |
| `CACHE_TTL_SECONDS` | `300` | Server cache duration in seconds |

---

## 🧪 API Endpoints

- `GET /board.png`: Returns high-contrast PNG image (`?force_refresh=true` or `?rotate=90`)
- `GET/POST /refresh`: Bypasses cache and forces immediate re-fetch from Flightradar24 API
- `GET /changed?hash=<HASH>`: Returns `{ "changed": true|false, "data_hash": "..." }`
- `GET /api/flights`: Returns raw JSON flight data
- `GET /status`: Returns last Flightradar24 API call status, HTTP response payload, and settings
- `GET /health`: Container health check

---

## 📄 License
MIT License. Open source and free to customize for homelab e-ink smart displays!
