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

logger = logging.getLogger("kindle-flight-board.flightservice")

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


class FlightService:
    """Service for fetching live airport schedules via FlightRadar24."""
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
        if raw_aircraft and isinstance(raw_aircraft, dict):
            model = raw_aircraft.get("model", {})
            if isinstance(model, dict):
                code = model.get("code") or model.get("text")
                if code:
                    return code
        idx = int(hashlib.md5(callsign.encode()).hexdigest(), 16) % len(AIRCRAFT_TYPES)
        return AIRCRAFT_TYPES[idx]

    def _format_local_time(self, epoch_sec: Optional[int]) -> str:
        """Format epoch timestamp to target timezone HH:MM."""
        if not epoch_sec:
            return "--:--"
        try:
            target_tz = tz.gettz(settings.TIMEZONE) or tz.tzutc()
            dt = datetime.fromtimestamp(epoch_sec, tz=timezone.utc).astimezone(target_tz)
            return dt.strftime("%H:%M")
        except Exception:
            return datetime.fromtimestamp(epoch_sec).strftime("%H:%M")

    def _generate_mock_flights(self, now: int) -> List[Flight]:
        """Generate 4 mock upcoming flights starting from current time forward."""
        logger.warning("Generating 4 mock upcoming flights for airport %s", settings.AIRPORT_ICAO)
        
        mock_raw = [
            ("DEP", "RYR9536", settings.AIRPORT_ICAO, "BRI", "B738", now + 600, "Estimated dep 23:50"),
            ("ARR", "WZZ5975", "BUD", settings.AIRPORT_ICAO, "A21N", now + 1800, "Estimated arr 00:10"),
            ("DEP", "WMT924", settings.AIRPORT_ICAO, "BGY", "A321", now + 3600, "Scheduled 01:00"),
            ("ARR", "ROT101", "OTP", settings.AIRPORT_ICAO, "E190", now + 5400, "Scheduled 01:30"),
        ]
        
        flights = []
        for flt_type, callsign, orig, dest, ac_type, ts, status_str in mock_raw:
            icao_prefix, airline_name, flt_num = self._get_airline_info({}, callsign)
            time_str = self._format_local_time(ts)
            
            flights.append(
                Flight(
                    callsign=callsign,
                    airline_icao=icao_prefix,
                    airline_name=airline_name,
                    flight_number=flt_num,
                    flight_type=flt_type,
                    origin=orig,
                    destination=dest,
                    aircraft_type=ac_type,
                    timestamp=ts,
                    scheduled_ts=ts,
                    scheduled_time=time_str,
                    estimated_time=time_str,
                    formatted_time=time_str,
                    status=status_str,
                    is_past=False
                )
            )
        return flights

    def get_flight_board(self, force_refresh: bool = False) -> FlightBoardData:
        """
        Fetch departures and arrivals from FlightRadar24, filter to ONLY 4 upcoming flights
        from the API call timestamp forward, and sort strictly by scheduled time.
        """
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
            
            upcoming_candidates: List[Tuple[int, Flight]] = []
            
            # Process Departures
            for item in raw_deps:
                flt = item.get("flight", {})
                if not flt:
                    continue
                
                times = flt.get("time", {})
                sched_ts = times.get("scheduled", {}).get("departure")
                est_ts = times.get("estimated", {}).get("departure") or times.get("real", {}).get("departure") or sched_ts
                if not sched_ts and not est_ts:
                    continue
                
                effective_ts = est_ts or sched_ts
                sort_ts = sched_ts or effective_ts
                status_raw = flt.get("status", {}).get("text") or "SCHEDULED"
                
                # Exclude past flights or already departed/canceled flights
                if sort_ts < (now - 300) or ("Departed" in status_raw) or ("Canceled" in status_raw):
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
                
                sched_str = self._format_local_time(sched_ts)
                est_str = self._format_local_time(est_ts) if est_ts else None
                
                upcoming_candidates.append((
                    sort_ts,
                    Flight(
                        icao24=ident.get("row") and str(ident.get("row")),
                        callsign=callsign,
                        airline_icao=icao_prefix,
                        airline_name=airline_name,
                        flight_number=formatted_flt_num,
                        flight_type="DEP",
                        origin=orig_code,
                        destination=dest_code,
                        aircraft_type=ac_type,
                        timestamp=effective_ts,
                        scheduled_ts=sort_ts,
                        scheduled_time=sched_str,
                        estimated_time=est_str,
                        formatted_time=sched_str,
                        status=status_raw,
                        is_past=False
                    )
                ))

            # Process Arrivals
            for item in raw_arrs:
                flt = item.get("flight", {})
                if not flt:
                    continue
                
                times = flt.get("time", {})
                sched_ts = times.get("scheduled", {}).get("arrival")
                est_ts = times.get("estimated", {}).get("arrival") or times.get("real", {}).get("arrival") or sched_ts
                if not sched_ts and not est_ts:
                    continue
                
                effective_ts = est_ts or sched_ts
                sort_ts = sched_ts or effective_ts
                status_raw = flt.get("status", {}).get("text") or "SCHEDULED"
                
                # Exclude past flights or already landed/canceled flights
                if sort_ts < (now - 300) or ("Landed" in status_raw) or ("Canceled" in status_raw):
                    continue
                
                ident = flt.get("identification", {})
                flt_num = ident.get("number", {}).get("default") or ident.get("callsign") or "N/A"
                callsign = ident.get("callsign") or flt_num
                
                raw_airline = flt.get("airline") or flt.get("owner") or {}
                icao_prefix, airline_name, formatted_flt_num = self._get_airline_info(raw_airline, callsign)
                
                raw_aircraft = flt.get("aircraft") or {}
                ac_type = self._get_aircraft_type(raw_aircraft, callsign)
                
                orig_code = flt.get("airport", {}).get("origin", {}).get("code", {}).get("iata") or \
                            flt.get("airport", {}).get("origin", {}).get("code", {}).get("icao") or \
                            flt.get("airport", {}).get("origin", {}).get("position", {}).get("region", {}).get("city") or "ORIG"
                
                dest_code = flt.get("airport", {}).get("destination", {}).get("code", {}).get("iata") or settings.AIRPORT_ICAO
                
                sched_str = self._format_local_time(sched_ts)
                est_str = self._format_local_time(est_ts) if est_ts else None
                
                upcoming_candidates.append((
                    sort_ts,
                    Flight(
                        icao24=ident.get("row") and str(ident.get("row")),
                        callsign=callsign,
                        airline_icao=icao_prefix,
                        airline_name=airline_name,
                        flight_number=formatted_flt_num,
                        flight_type="ARR",
                        origin=orig_code,
                        destination=dest_code,
                        aircraft_type=ac_type,
                        timestamp=effective_ts,
                        scheduled_ts=sort_ts,
                        scheduled_time=sched_str,
                        estimated_time=est_str,
                        formatted_time=sched_str,
                        status=status_raw,
                        is_past=False
                    )
                ))

            # Sort strictly by scheduled_ts ascending and pick ONLY the next 4 flights
            upcoming_candidates.sort(key=lambda x: x[0])
            flights_list = [f[1] for f in upcoming_candidates[:4]]
                
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

        # Fallback to mock data if API returned zero upcoming flights
        if len(flights_list) < 4 and settings.USE_MOCK_DATA_ON_FAILURE:
            flights_list = self._generate_mock_flights(now)

        # Build data hash
        last_updated_str = datetime.now(target_tz).strftime("%Y-%m-%d %H:%M:%S")
        raw_hash_str = f"{settings.AIRPORT_ICAO}-" + "-".join([f"{f.flight_type}:{f.callsign}:{f.scheduled_ts}:{f.status}" for f in flights_list])
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
            if isinstance(value, Path):
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


flight_service = FlightService()
