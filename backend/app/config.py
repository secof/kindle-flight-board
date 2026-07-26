from pydantic_settings import BaseSettings
from pydantic import Field
import os
from pathlib import Path


class Settings(BaseSettings):
    # Airport Settings
    AIRPORT_ICAO: str = Field(default="KJFK", description="ICAO code for target airport (e.g. KLAX, EGLL, KJFK)")
    AIRPORT_NAME: str = Field(default="John F. Kennedy Intl", description="Display name for airport header")
    TIMEZONE: str = Field(default="America/New_York", description="Timezone name for display timestamps")
    
    # OpenSky Network API Credentials (Optional, increases API rate limits)
    OPENSKY_USERNAME: str = Field(default="", description="OpenSky Network username")
    OPENSKY_PASSWORD: str = Field(default="", description="OpenSky Network password")
    
    # Display Settings (Kindle Paperwhite FW 5.17)
    BOARD_WIDTH: int = Field(default=1448, description="Target image width in pixels")
    BOARD_HEIGHT: int = Field(default=1072, description="Target image height in pixels")
    ROTATE_DEGREES: int = Field(default=0, description="Rotation degrees: 0, 90, 180, 270")
    INVERT_COLORS: bool = Field(default=False, description="Invert black/white for dark mode e-ink display")
    
    # Polling & Cache Settings
    CACHE_TTL_SECONDS: int = Field(default=300, description="Cache OpenSky responses for 5 minutes")
    USE_MOCK_DATA_ON_FAILURE: bool = Field(default=True, description="Fallback to mockup flight data if OpenSky fails/rate-limited")
    
    # File Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    ASSETS_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "assets")
    LOGOS_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "assets" / "logos")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
