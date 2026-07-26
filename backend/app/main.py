import logging
from fastapi import FastAPI, Query, Response, Header
from fastapi.responses import JSONResponse, Response
from typing import Optional

from app.config import settings
from app.flight_service import flight_service
from app.renderer import renderer
from app.models import ChangedStatus, FlightBoardData

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("kindle-flight-board")

app = FastAPI(
    title="Kindle Flight Board Backend",
    description="Backend API serving live flight data images for Kindle e-ink display",
    version="1.0.0"
)


@app.get("/health")
def health_check():
    """Health check endpoint for Unraid/Docker containers."""
    return {
        "status": "online",
        "airport_icao": settings.AIRPORT_ICAO,
        "airport_name": settings.AIRPORT_NAME,
        "board_dimensions": f"{settings.BOARD_WIDTH}x{settings.BOARD_HEIGHT}"
    }


@app.get("/status")
def get_status():
    """
    Returns system status including the last call to FlightRadar24 API,
    the response received, and all active app settings.
    """
    return flight_service.get_status()


@app.get("/changed", response_model=ChangedStatus)
def check_changed(
    client_hash: Optional[str] = Query(None, alias="hash", description="SHA256 hash currently held by Kindle"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match")
):
    """
    Lightweight endpoint for Kindle daemon to check if board data has changed.
    Avoids unnecessary image downloads to conserve Kindle battery & e-ink cycles.
    """
    board_data = flight_service.get_flight_board()
    target_hash = client_hash or (if_none_match.strip('"') if if_none_match else None)
    
    has_changed = (target_hash != board_data.data_hash)
    
    return ChangedStatus(
        changed=has_changed,
        data_hash=board_data.data_hash,
        last_updated=board_data.last_updated
    )


@app.get("/board.png")
def get_board_image(
    force_refresh: bool = Query(False, description="Bypass cache and force re-fetch from FlightRadar24"),
    rotate: Optional[int] = Query(None, description="Override image rotation (0, 90, 180, 270)")
):
    """
    Render and serve high-contrast landscape/portrait PNG image for Kindle display.
    """
    board_data = flight_service.get_flight_board(force_refresh=force_refresh)
    image_bytes = renderer.render(board_data, rotate_override=rotate)
    
    headers = {
        "Cache-Control": "public, max-age=60",
        "ETag": f'"{board_data.data_hash}"',
        "X-Flight-Count": str(len(board_data.flights)),
        "X-Data-Hash": board_data.data_hash
    }
    
    return Response(content=image_bytes, media_type="image/png", headers=headers)


@app.get("/api/flights", response_model=FlightBoardData)
def get_flights_json():
    """Returns raw structured flight data in JSON format."""
    return flight_service.get_flight_board()
