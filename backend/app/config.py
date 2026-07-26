from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[
            str(ROOT_DIR / ".env"),
            str(BASE_DIR / ".env"),
            ".env"
        ],
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Airport Settings
    AIRPORT_ICAO: str = Field(default="KJFK", description="ICAO code for target airport (e.g. KLAX, EGLL, KJFK)")
    AIRPORT_NAME: str = Field(default="John F. Kennedy Intl", description="Display name for airport header")
    TIMEZONE: str = Field(default="America/New_York", description="Timezone name for display timestamps")
    
    # Display Settings (Kindle Paperwhite 10th Gen)
    BOARD_WIDTH: int = Field(default=1072, description="Target image width in pixels for Kindle Paperwhite 10")
    BOARD_HEIGHT: int = Field(default=1448, description="Target image height in pixels for Kindle Paperwhite 10")
    ROTATE_DEGREES: int = Field(default=90, description="Rotation degrees: 0, 90, 180, 270")
    INVERT_COLORS: bool = Field(default=False, description="Invert black/white for dark mode e-ink display")
    
    # Polling & Cache Settings
    CACHE_TTL_SECONDS: int = Field(default=300, description="Cache FlightRadar24 responses for 5 minutes")
    USE_MOCK_DATA_ON_FAILURE: bool = Field(default=True, description="Fallback to mockup flight data if FlightRadar24 fails")
    
    # File Paths
    ASSETS_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "assets")
    LOGOS_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "assets" / "logos")


settings = Settings()
