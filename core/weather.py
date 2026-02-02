from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import requests

# Open-Meteo API endpoints
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
CURRENT_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def geocode_list(query: str, count: int = 5) -> List[Dict[str, Any]]:
    """Search for locations by name using Open-Meteo geocoding."""
    resp = requests.get(
        GEOCODE_URL,
        params={"name": query, "count": count, "language": "en", "format": "json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [])


def fetch_current_temp(lat: float, lon: float) -> Optional[float]:
    """Fetch current temperature for a location."""
    try:
        resp = requests.get(
            CURRENT_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("current_weather", {}).get("temperature")
    except Exception:
        return None


def fetch_current_weather(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetch current weather conditions including:
    - Current temperature
    - Wind speed
    """
    try:
        resp = requests.get(
            CURRENT_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        cw = data.get("current_weather", {})
        return {
            "current_temp": cw.get("temperature"),
            "wind_speed": cw.get("windspeed"),  # km/h
            "wind_direction": cw.get("winddirection"),
        }
    except Exception:
        return {"current_temp": None, "wind_speed": None, "wind_direction": None}


def fetch_design_climate(lat: float, lon: float, years: int = 10) -> Dict[str, Any]:
    """
    Fetch historical climate data for PV design:
    - Tmin: Lowest temperature in the last N years (for overvoltage check)
    - Tmax: Highest temperature in the last N years (for derating)
    - Max wind speed: Highest wind gust (for structural design)
    
    Returns dict with values and method description.
    """
    from datetime import datetime, timedelta

    end_date = datetime.now() - timedelta(days=7)  # Archive has ~1 week delay
    start_date = end_date - timedelta(days=years * 365)

    result = {
        "tmin": None,
        "tmax": None,
        "max_wind_speed": None,
        "method": "",
    }

    try:
        resp = requests.get(
            ARCHIVE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "daily": "temperature_2m_min,temperature_2m_max,wind_gusts_10m_max",
                "timezone": "auto",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        t_mins = daily.get("temperature_2m_min", [])
        t_maxs = daily.get("temperature_2m_max", [])
        wind_gusts = daily.get("wind_gusts_10m_max", [])

        # Filter out None values
        t_mins = [t for t in t_mins if t is not None]
        t_maxs = [t for t in t_maxs if t is not None]
        wind_gusts = [w for w in wind_gusts if w is not None]

        if t_mins:
            result["tmin"] = min(t_mins)
        if t_maxs:
            result["tmax"] = max(t_maxs)
        if wind_gusts:
            result["max_wind_speed"] = max(wind_gusts)

        result["method"] = f"Archive: {years}Y historical data ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})"

    except Exception as e:
        result["method"] = f"Archive: failed to fetch data ({str(e)[:50]})"

    return result


def fetch_design_tmin(lat: float, lon: float, years: int = 10) -> Tuple[Optional[float], str]:
    """
    Legacy function for backward compatibility.
    Returns (tmin, method_description).
    """
    climate = fetch_design_climate(lat, lon, years)
    return climate["tmin"], climate["method"]