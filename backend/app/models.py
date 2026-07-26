from pydantic import BaseModel, Field
from typing import List, Optional


class Flight(BaseModel):
    icao24: Optional[str] = Field(default=None, description="Transponder ICAO 24-bit address or row ID")
    callsign: str = Field(..., description="Flight callsign / number")
    airline_icao: str = Field(..., description="3-letter ICAO airline code (e.g. RYR, WZZ, ROT)")
    airline_name: str = Field(default="Airline", description="Readable airline name")
    flight_number: str = Field(..., description="Formatted flight number (e.g. FR 9537, W6 3291)")
    flight_type: str = Field(default="DEP", description="Flight type: DEP (Departure) or ARR (Arrival)")
    origin: str = Field(..., description="Origin airport code or city")
    destination: str = Field(..., description="Destination airport code or city")
    aircraft_type: str = Field(default="A320", description="Aircraft model code (e.g. B738, A321, A21N)")
    timestamp: int = Field(..., description="Effective departure/arrival epoch timestamp")
    scheduled_time: str = Field(..., description="Scheduled local time HH:MM")
    estimated_time: Optional[str] = Field(default=None, description="Estimated/real local time HH:MM if available")
    formatted_time: str = Field(..., description="Formatted local display time HH:MM")
    status: str = Field(..., description="Flight status text (e.g. Delayed 23:11, Estimated dep 23:50)")
    is_past: bool = Field(default=False, description="True if flight completed in the past")


class FlightBoardData(BaseModel):
    airport_icao: str
    airport_name: str
    last_updated: str
    flights: List[Flight]  # Exactly 4 upcoming flights
    data_hash: str


class ChangedStatus(BaseModel):
    changed: bool
    data_hash: str
    last_updated: str
