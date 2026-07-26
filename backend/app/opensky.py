import time
import hashlib
import logging
from typing import List, Tuple, Dict, Optional, Any
from datetime import datetime, timezone
from pathlib import Path
from dateutil import tz
from FlightRadarAPI import FlightRadar24API

from app.config import settings
from app.models import Flight, FlightBoardData

logger = logging.getLogger("kindle-flight-board.flightradar")

# Mapping common ICAO airline prefixes to names & IATA prefixes
AIRLINE_MAP: Dict[str, Tuple[str, str]] = {
    "AAL": ("American Airlines", "AA"),
    "DAL": ("Delta Air Lines", "DL"),
    "UAL": ("United Airlines", "UA"),
    "DLH": ("Lufthansa", "LH"),
    "BAW": ("British Airways", "BA"),
    "AFR": ("Air France", "AF"),
    "KLM": ("KLM", "KL"),
    "SWR": ("Swiss Intl Air Lines", "LX"),
    "UAE": ("Emirates", "EK"),
    "QFA": ("Qantas", "QF"),
    "VIR": ("Virgin Atlantic", "VS"),
    "EIN": ("Aer Lingus", "EI"),
    "IBE": ("Iberia", "IB"),
    "ACA": ("Air Canada", "AC"),
    "ANA": ("All Nippon Airways", "NH"),
    "JAL": ("Japan Airlines", "JL"),
    "SAS": ("Scandinavian Airlines", "SK"),
    "TAP": ("TAP Air Portugal", "TP"),
    "RYR": ("Ryanair", "FR"),
    "EZY": ("EasyJet", "U2"),
    "ROT": ("TAROM", "RO"),
    "WZZ": ("Wizz Air", "W6"),
    "WMT": ("Wizz Air Malta", "W4"),
}

AIRCRAFT_TYPES = ["A320", "B738", "A321", "B789", "A359", "B77W", "A333", "B763", "E190", "A20N"]


class OpenSkyClient:
    """Client for fetching live airport schedules via FlightRadar24."""
    def __init__(self):
        self.fr_api = FlightRadar24API()
        self._cache_data: Optional[FlightBoardData] = None
        self._cache_timestamp: float = 0.0
        self.last_api_call: Optional[Dict[str, Any]] = None

    def _get_airline_info(self, raw_airline: dict, callsign: str) -> Tuple[str, str, str]:
        """Extract ICAO prefix, human name, and formatted flight number."""
        icao_code = raw_airline.get("code", {}).get("icao") if raw_airline else None
        airline_name = raw_airline.get("name") if raw_airline else None
        
        clean_callsign = callsign.strip().upper()
        if not icao_code and len(clean_callsign) >= 3:
            icao_code = clean_callsign[:3]
            
        if icao_code in AIRLINE_MAP:
            mapped_name, iata_prefix = AIRLINE_MAP[icao_code]
            name = airline_name or mapped_name
            flight_num = f"{iata_prefix} {clean_callsign[3:]}" if clean_callsign.startswith(icao_code) else clean_callsign
            return icao_code, name, flight_num

        return (icao_code or "DEFAULT"), (airline_name or f"Airline ({icao_code or 'UNK'})"), clean_callsign

    def _get_aircraft_type(self, raw_aircraft: dict, callsign: str) -> str:
        """Extract or infer aircraft model code."""
        code = raw_aircraft.get("model", {}).get("code") if raw_aircraft else None
        if code:
            return code
        idx = int(hashlib.md5(callsign.encode()).hexdigest(), 16) % len(AIRCRAFT_TYPES)
        return AIRCRAFT_TYPES[idx]

    def _format_local_time(self, epoch_sec: int) -> str:
        """Format epoch timestamp to target timezone HH:MM."""
        try:
            target_tz = tz.gettz(settings.TIMEZONE) or tz.tzutc()
            dt = datetime.fromtimestamp(epoch_sec, tz=timezone.utc).astimezone(target_tz)
            return dt.strftime("%H:%M")
        except Exception:
            return datetime.fromtimestamp(epoch_sec).strftime("%H:%M")

    def _generate_mock_flights(self, now: int) -> List[Flight]:
        """Generate realistic mock data if API is down or rate limited."""
        logger.warning("Generating mock flight dataset for airport %s", settings.AIRPORT_ICAO)
        
        mock_raw = [
            ("AAL100", settings.AIRPORT_ICAO, "EGLL", now - 1200, "DEPARTED"),
            ("DLH400", settings.AIRPORT_ICAO, "EDDF", now + 900, "BOARDING"),
            ("BAW178", settings.AIRPORT_ICAO, "EGLL", now + 2400, "SCHEDULED"),
            ("AFR007", settings.AIRPORT_ICAO, "LFPG", now + 4200, "SCHEDULED"),
        ]
        
        flights = []
        for callsign, orig, dest, ts, status_str in mock_raw:
            icao_prefix, airline_name, flt_num = self._get_airline_info({}, callsign)
            ac_type = self._get_aircraft_type({}, callsign)
            is_past = ts < now
            time_str = self._format_local_time(ts)
            
            status = f"{status_str} {time_str}" if is_past or status_str == "BOARDING" else f"SCHED {time_str}"
            
            flights.append(
                Flight(
                    callsign=callsign,
                    airline_icao=icao_prefix,
                    airline_name=airline_name,
                    flight_number=flt_num,
                    origin=orig,
                    destination=dest,
                    aircraft_type=ac_type,
                    timestamp=ts,
                    formatted_time=time_str,
                    status=status,
                    is_past=is_past
                )
            )
        return flights

    def get_flight_board(self, force_refresh: bool = False) -> FlightBoardData:
        """Fetch live departure/arrival flights via FlightRadar24, filter to 1 past + 3 future, and format."""
        now = int(time.time())
        target_tz = tz.gettz(settings.TIMEZONE) or tz.tzutc()
        
        # Check cache
        if not force_refresh and self._cache_data and (now - self._cache_timestamp < settings.CACHE_TTL_SECONDS):
            return self._cache_data

        flights_list: List[Flight] = []
        call_time_str = datetime.now(target_tz).strftime("%Y-%m-%d %H:%M:%S %Z")
        
        try:
            details = self.fr_api.get_airport_details(settings.AIRPORT_ICAO)
            airport_obj = details.get("airport", {}) if details else {}
            schedule = airport_obj.get("pluginData", {}).get("schedule", {}) if airport_obj else {}
            
            raw_deps = schedule.get("departures", {}).get("data", [])
            raw_arrs = schedule.get("arrivals", {}).get("data", [])
            
            self.last_api_call = {
                "requested_at": call_time_str,
                "source": "Flightradar24",
                "airport": settings.AIRPORT_ICAO,
                "status_code": 200 if details else 404,
                "departures_count": len(raw_deps),
                "arrivals_count": len(raw_arrs),
                "raw_deps_sample": [d.get("flight", {}).get("identification", {}).get("number", {}).get("default") for d in raw_deps[:3]],
                "raw_arrs_sample": [a.get("flight", {}).get("identification", {}).get("number", {}).get("default") for a in raw_arrs[:3]],
                "error": None if details else f"Airport details not found for {settings.AIRPORT_ICAO}"
            }
            
            parsed_flights: List[Flight] = []
            
            # Combine departures and arrivals if needed (prioritizing departures)
            items_to_process = raw_deps if raw_deps else raw_arrs
            
            for item in items_to_process:
                flt = item.get("flight", {})
                if not flt:
                    continue
                
                ident = flt.get("identification", {})
                flt_num = ident.get("number", {}).get("default") or ident.get("callsign") or "N/A"
                callsign = ident.get("callsign") or flt_num
                
                raw_airline = flt.get("airline") or flt.get("owner") or {}
                icao_prefix, airline_name, formatted_flt_num = self._get_airline_info(raw_airline, callsign)
                
                raw_aircraft = flt.get("aircraft") or {}
                ac_type = self._get_aircraft_type(raw_aircraft, callsign)
                
                dest_code = flt.get("airport", {}).get("destination", {}).get("code", {}).get("iata") or \
                            flt.get("airport", {}).get("destination", {}).get("code", {}).get("icao") or \
                            flt.get("airport", {}).get("destination", {}).get("position", {}).get("region", {}).get("city") or "DEST"
                
                orig_code = flt.get("airport", {}).get("origin", {}).get("code", {}).get("iata") or settings.AIRPORT_ICAO
                
                times = flt.get("time", {})
                dep_time = times.get("real", {}).get("departure") or \
                           times.get("estimated", {}).get("departure") or \
                           times.get("scheduled", {}).get("departure") or now
                
                time_str = self._format_local_time(dep_time)
                status_raw = flt.get("status", {}).get("text") or "SCHEDULED"
                
                is_past = (dep_time < now) or ("Departed" in status_raw) or ("Landed" in status_raw)
                
                parsed_flights.append(
                    Flight(
                        icao24=ident.get("row") and str(ident.get("row")),
                        callsign=callsign,
                        airline_icao=icao_prefix,
                        airline_name=airline_name,
                        flight_number=formatted_flt_num,
                        origin=orig_code,
                        destination=dest_code,
                        aircraft_type=ac_type,
                        timestamp=dep_time,
                        formatted_time=time_str,
                        status=status_raw,
                        is_past=is_past
                    )
                )
            
            if parsed_flights:
                past_flights = sorted([f for f in parsed_flights if f.is_past], key=lambda x: x.timestamp, reverse=True)
                future_flights = sorted([f for f in parsed_flights if not f.is_past], key=lambda x: x.timestamp)
                
                selected: List[Flight] = []
                if past_flights:
                    selected.append(past_flights[0])
                
                needed_future = 4 - len(selected)
                selected.extend(future_flights[:needed_future])
                
                if len(selected) < 4:
                    remaining_past = [p for p in past_flights if p not in selected]
                    selected.extend(remaining_past[:4 - len(selected)])
                
                flights_list = sorted(selected, key=lambda x: x.timestamp)
                
        except Exception as e:
            logger.error("Failed to query FlightRadar24 API: %s", str(e))
            self.last_api_call = {
                "requested_at": call_time_str,
                "source": "Flightradar24",
                "airport": settings.AIRPORT_ICAO,
                "status_code": 500,
                "departures_count": 0,
                "arrivals_count": 0,
                "error": str(e)
            }

        # Fallback to mock data if API returned zero flights
        if len(flights_list) < 4 and settings.USE_MOCK_DATA_ON_FAILURE:
            flights_list = self._generate_mock_flights(now)

        # Build data hash
        last_updated_str = datetime.now(target_tz).strftime("%Y-%m-%d %H:%M:%S")
        raw_hash_str = f"{settings.AIRPORT_ICAO}-" + "-".join([f"{f.callsign}:{f.timestamp}:{f.status}" for f in flights_list])
        data_hash = hashlib.sha256(raw_hash_str.encode()).hexdigest()[:16]

        board_data = FlightBoardData(
            airport_icao=settings.AIRPORT_ICAO,
            airport_name=settings.AIRPORT_NAME,
            last_updated=last_updated_str,
            flights=flights_list,
            data_hash=data_hash
        )
        
        self._cache_data = board_data
        self._cache_timestamp = now
        return board_data

    def get_status(self) -> Dict[str, Any]:
        """Return system status including active app settings and the last FlightRadar24 API call."""
        target_tz = tz.gettz(settings.TIMEZONE) or tz.tzutc()
        current_time_str = datetime.now(target_tz).strftime("%Y-%m-%d %H:%M:%S %Z")
        
        app_settings = {}
        for key, value in settings.model_dump().items():
            if key == "OPENSKY_PASSWORD" and value:
                app_settings[key] = "********"
            elif isinstance(value, Path):
                app_settings[key] = str(value)
            else:
                app_settings[key] = value

        return {
            "status": "online",
            "provider": "Flightradar24 API",
            "current_time": current_time_str,
            "last_flightradar_call": self.last_api_call or "No call made yet (endpoint has not been queried)",
            "app_settings": app_settings
        }


opensky_client = OpenSkyClient()
