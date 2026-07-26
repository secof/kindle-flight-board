from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class Flight(BaseModel):
    icao24: Optional[str] = Field(default=None, description="Transponder ICAO 24-bit address")
    callsign: str = Field(..., description="Flight callsign / number (e.g. AAL100, DLH400)")
    airline_icao: str = Field(..., description="3-letter ICAO airline code (e.g. AAL, DLH, BAW)")
    airline_name: str = Field(default="Airline", description="Readable airline name")
    flight_number: str = Field(..., description="Formatted flight number (e.g. AA 100, LH 400)")
    origin: str = Field(..., description="Origin airport ICAO or IATA code")
    destination: str = Field(..., description="Destination airport ICAO or IATA code")
    aircraft_type: str = Field(default="A320", description="Aircraft type designator (e.g. A320, B738, B789)")
    timestamp: int = Field(..., description="Flight departure/arrival epoch timestamp")
    formatted_time: str = Field(..., description="Formatted local time (e.g. 14:25)")
    status: str = Field(..., description="Flight status (e.g. DEPARTED 14:10, SCHEDULED, BOARDING)")
    is_past: bool = Field(default=False, description="True if flight departed/arrived in the past")


class FlightBoardData(BaseModel):
    airport_icao: str
    airport_name: str
    last_updated: str
    flights: List[Flight]  # Exactly 4 flights: 1 past, 3 future
    data_hash: str


class ChangedStatus(BaseModel):
    changed: bool
    data_hash: str
    last_updated: str
