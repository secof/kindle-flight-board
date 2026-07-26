import time
import hashlib
import logging
from typing import List, Tuple, Dict, Optional
from datetime import datetime, timezone
import requests
from dateutil import tz

from app.config import settings
from app.models import Flight, FlightBoardData

logger = logging.getLogger("kindle-flight-board.opensky")

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
}

# Aircraft type fallback map based on random hash or icao24 prefix
AIRCRAFT_TYPES = ["A320", "B738", "A321", "B789", "A359", "B77W", "A333", "B763", "E190", "A20N"]


class OpenSkyClient:
    def __init__(self):
        self.session = requests.Session()
        if settings.OPENSKY_USERNAME and settings.OPENSKY_PASSWORD:
            self.session.auth = (settings.OPENSKY_USERNAME, settings.OPENSKY_PASSWORD)
        
        self._cache_data: Optional[FlightBoardData] = None
        self._cache_timestamp: float = 0.0

    def _get_airline_info(self, callsign: str) -> Tuple[str, str, str]:
        """Extract ICAO prefix, human name, and formatted flight number from callsign."""
        clean_callsign = callsign.strip().upper()
        if len(clean_callsign) >= 3:
            icao_prefix = clean_callsign[:3]
            if icao_prefix in AIRLINE_MAP:
                name, iata_prefix = AIRLINE_MAP[icao_prefix]
                flight_num = iata_prefix + " " + clean_callsign[3:]
                return icao_prefix, name, flight_num
            return icao_prefix, f"Airline ({icao_prefix})", clean_callsign
        return "DEFAULT", "Unknown Airline", clean_callsign

    def _get_aircraft_type(self, icao24: Optional[str]) -> str:
        """Infer or map aircraft type from icao24 code."""
        if not icao24:
            return "A320"
        idx = int(hashlib.md5(icao24.encode()).hexdigest(), 16) % len(AIRCRAFT_TYPES)
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
        """Generate realistic mock data if OpenSky API is down or rate limited."""
        logger.warning("Generating mock flight dataset for airport %s", settings.AIRPORT_ICAO)
        
        mock_raw = [
            ("AAL100", settings.AIRPORT_ICAO, "EGLL", now - 1200, "DEPARTED"),
            ("DLH400", settings.AIRPORT_ICAO, "EDDF", now + 900, "BOARDING"),
            ("BAW178", settings.AIRPORT_ICAO, "EGLL", now + 2400, "SCHEDULED"),
            ("AFR007", settings.AIRPORT_ICAO, "LFPG", now + 4200, "SCHEDULED"),
        ]
        
        flights = []
        for callsign, orig, dest, ts, status_str in mock_raw:
            icao_prefix, airline_name, flt_num = self._get_airline_info(callsign)
            ac_type = self._get_aircraft_type(callsign)
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
        """Fetch departure/arrival flights, filter to 1 past + 3 future, and format."""
        now = int(time.time())
        
        # Check cache
        if not force_refresh and self._cache_data and (now - self._cache_timestamp < settings.CACHE_TTL_SECONDS):
            return self._cache_data

        flights_list: List[Flight] = []
        
        try:
            # Query OpenSky departures endpoint
            url = "https://opensky-network.org/api/flights/departure"
            params = {
                "airport": settings.AIRPORT_ICAO,
                "begin": now - 3600 * 2,  # 2 hours past
                "end": now + 3600 * 4      # 4 hours future
            }
            resp = self.session.get(url, params=params, timeout=8)
            
            if resp.status_code == 200:
                raw_flights = resp.json()
                parsed_flights: List[Flight] = []
                
                for item in raw_flights:
                    callsign = (item.get("callsign") or "").strip()
                    if not callsign:
                        continue
                    
                    est_dep = item.get("firstSeen") or item.get("lastSeen") or now
                    est_arr = item.get("estDepartureAirport")
                    est_dest = item.get("estArrivalAirport") or "DEST"
                    icao24 = item.get("icao24")
                    
                    icao_prefix, airline_name, flt_num = self._get_airline_info(callsign)
                    ac_type = self._get_aircraft_type(icao24)
                    is_past = est_dep < now
                    time_str = self._format_local_time(est_dep)
                    
                    status = f"DEPARTED {time_str}" if is_past else f"SCHED {time_str}"
                    
                    parsed_flights.append(
                        Flight(
                            icao24=icao24,
                            callsign=callsign,
                            airline_icao=icao_prefix,
                            airline_name=airline_name,
                            flight_number=flt_num,
                            origin=settings.AIRPORT_ICAO,
                            destination=est_dest,
                            aircraft_type=ac_type,
                            timestamp=est_dep,
                            formatted_time=time_str,
                            status=status,
                            is_past=is_past
                        )
                    )
                
                if parsed_flights:
                    # Select 1 PAST flight (highest timestamp < now)
                    past_flights = sorted([f for f in parsed_flights if f.timestamp <= now], key=lambda x: x.timestamp, reverse=True)
                    # Select 3 FUTURE flights (lowest timestamp > now)
                    future_flights = sorted([f for f in parsed_flights if f.timestamp > now], key=lambda x: x.timestamp)
                    
                    selected: List[Flight] = []
                    if past_flights:
                        selected.append(past_flights[0])
                    
                    # Fill future flights up to total 4
                    needed_future = 4 - len(selected)
                    selected.extend(future_flights[:needed_future])
                    
                    # If we still lack 4 total flights, fill with remaining past flights or mocks
                    if len(selected) < 4:
                        remaining_past = [p for p in past_flights if p not in selected]
                        selected.extend(remaining_past[:4 - len(selected)])
                    
                    flights_list = sorted(selected, key=lambda x: x.timestamp)

            else:
                logger.warning("OpenSky API returned status %d: %s", resp.status_code, resp.text[:100])
        except Exception as e:
            logger.error("Failed to query OpenSky API: %s", str(e))

        # Fallback to mock data if OpenSky returned insufficient flights
        if len(flights_list) < 4 and settings.USE_MOCK_DATA_ON_FAILURE:
            flights_list = self._generate_mock_flights(now)

        # Build data hash
        target_tz = tz.gettz(settings.TIMEZONE) or tz.tzutc()
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


opensky_client = OpenSkyClient()
