from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from constants import (
    DEFAULT_TIMEOUT_SECONDS,
    GEOCODE_API_URL,
    MET_NO_API_URL,
    OPEN_METEO_API_URL,
    USER_AGENT,
    WTTR_API_URL,
)
from weather_app.models import Location


Fetcher = Callable[[Location], dict]


def fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS, headers: dict[str, str] | None = None) -> dict:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if headers:
        request_headers.update(headers)

    req = Request(url, headers=request_headers)
    with urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def geocode_city(city: str) -> Location:
    url = f"{GEOCODE_API_URL}?name={quote(city)}&count=1&language=en&format=json"
    data = fetch_json(url)
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Could not geocode city: {city}")

    first = results[0]
    return Location(
        city=first.get("name", city),
        latitude=float(first["latitude"]),
        longitude=float(first["longitude"]),
    )


def fetch_open_meteo(location: Location) -> dict:
    url = (
        f"{OPEN_METEO_API_URL}"
        f"?latitude={location.latitude}&longitude={location.longitude}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m"
        "&timezone=auto"
    )
    data = fetch_json(url)
    current = data.get("current", {})
    return {
        "source": "Open-Meteo",
        "city": location.city,
        "time": current.get("time"),
        "temperature_c": current.get("temperature_2m"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "feels_like_c": current.get("apparent_temperature"),
        "wind_kmh": current.get("wind_speed_10m"),
    }


def fetch_wttr(location: Location) -> dict:
    url = f"{WTTR_API_URL}/{quote(location.city)}?format=j1"
    data = fetch_json(url)
    current = (data.get("current_condition") or [{}])[0]

    def num_or_text(key: str):
        value = current.get(key)
        if value is None:
            return None
        try:
            if "." in str(value):
                return float(value)
            return int(value)
        except ValueError:
            return value

    # Get observation time from API data, not current system time
    obs_time = None
    nearest_area = (data.get("nearest_area") or [{}])[0]
    if nearest_area:
        current_condition_list = nearest_area.get("current_condition", [])
        if current_condition_list:
            obs_time = current_condition_list[0].get("observation_time")

    return {
        "source": "wttr.in",
        "city": location.city,
        "time": obs_time or datetime.now(timezone.utc).isoformat(),
        "temperature_c": num_or_text("temp_C"),
        "humidity_percent": num_or_text("humidity"),
        "feels_like_c": num_or_text("FeelsLikeC"),
        "wind_kmh": num_or_text("windspeedKmph"),
        "weather": ((current.get("weatherDesc") or [{}])[0]).get("value"),
    }


def fetch_met_no(location: Location) -> dict:
    url = f"{MET_NO_API_URL}?lat={location.latitude}&lon={location.longitude}"
    data = fetch_json(url)
    timeseries = data.get("properties", {}).get("timeseries", [])
    if not timeseries:
        raise ValueError("met.no response missing time series data")

    first = timeseries[0]
    details = first.get("data", {}).get("instant", {}).get("details", {})
    return {
        "source": "MET Norway",
        "city": location.city,
        "time": first.get("time"),
        "temperature_c": details.get("air_temperature"),
        "humidity_percent": details.get("relative_humidity"),
        "wind_kmh": details.get("wind_speed") * 3.6 if details.get("wind_speed") is not None else None,
        "pressure_hpa": details.get("air_pressure_at_sea_level"),
    }


def get_fetchers() -> list[Fetcher]:
    return [fetch_open_meteo, fetch_wttr, fetch_met_no]


def fetch_all_sources(location: Location) -> tuple[list[dict], dict]:
    """Fetch all sources and compute stats concurrently with thread-safe locks.
    
    Stats (min/max/avg temperature) are computed inside the ThreadPoolExecutor
    using locks to safely update shared state as each fetch completes.
    
    Returns:
        Tuple of (results list, stats dict with min/max/avg temperature)
    """
    # Shared state for stats computation (using dict to avoid nonlocal issues)
    stats_lock = threading.Lock()
    stats_accumulator = {
        "min_temp": float('inf'),
        "max_temp": float('-inf'),
        "sum_temp": 0.0,
        "count_temps": 0,
    }
    
    fetchers = get_fetchers()
    results: list[dict] = []
    
    def process_fetch(fetcher: Fetcher, location: Location) -> tuple[dict, float | None]:
        """Fetch and return result with temperature if available."""
        try:
            result = fetcher(location)
            temp = result.get("temperature_c") if "error" not in result else None
            return result, temp
        except Exception as exc:
            return {"source": fetcher.__name__, "error": str(exc)}, None
    
    with ThreadPoolExecutor(max_workers=len(fetchers)) as executor:
        future_map = {executor.submit(process_fetch, fetcher, location): fetcher.__name__ for fetcher in fetchers}
        
        for future in as_completed(future_map):
            result, temp = future.result()
            results.append(result)
            
            # Thread-safe update of stats using lock
            if temp is not None:
                with stats_lock:
                    stats_accumulator["min_temp"] = min(stats_accumulator["min_temp"], float(temp))
                    stats_accumulator["max_temp"] = max(stats_accumulator["max_temp"], float(temp))
                    stats_accumulator["sum_temp"] += float(temp)
                    stats_accumulator["count_temps"] += 1
    
    # Compute final stats from accumulated values
    count = stats_accumulator["count_temps"]
    stats = {
        "min_temp": round(stats_accumulator["min_temp"], 1) if count > 0 else None,
        "max_temp": round(stats_accumulator["max_temp"], 1) if count > 0 else None,
        "avg_temp": round(stats_accumulator["sum_temp"] / count, 1) if count > 0 else None,
    }
    return results, stats


def format_result(result: dict) -> str:
    source = result.get("source", "unknown")
    city = result.get("city", "unknown")
    time_value = result.get("time", "n/a")
    temp = result.get("temperature_c", "n/a")
    humidity = result.get("humidity_percent", "n/a")
    wind = result.get("wind_kmh", "n/a")

    extras = []
    if result.get("feels_like_c") is not None:
        extras.append(f"feels_like={result['feels_like_c']}°C")
    if result.get("weather"):
        extras.append(f"weather={result['weather']}")
    if result.get("pressure_hpa") is not None:
        extras.append(f"pressure={result['pressure_hpa']} hPa")

    suffix = f" | {'; '.join(extras)}" if extras else ""
    return (
        f"[{source}] city={city} time={time_value} "
        f"temp={temp}°C humidity={humidity}% wind={wind} km/h{suffix}"
    )
