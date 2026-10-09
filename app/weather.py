"""Weather for the Today page, from Open-Meteo (free, no API key).

The location is a setting (planner_db app_settings), defaulting to Latrobe,
PA. Forecasts are cached in-process for a few minutes so the page never
waits on, or hammers, the upstream API; if a refresh fails the last good
forecast is served instead of an error.
"""

import time

import httpx

from app import planner_db

DEFAULT_LOCATION = {"name": "Latrobe, PA", "latitude": 40.32118, "longitude": -79.37948}
SETTING_KEY = "weather_location"

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_CACHE_TTL_SECONDS = 15 * 60
_cache: dict[tuple[float, float], tuple[float, dict]] = {}

# WMO weather interpretation codes -> (label, icon). The icon is one of a
# handful of names the frontend draws; keeping the mapping here means the
# page doesn't need to know WMO codes.
_CODES = {
    0: ("Clear", "clear"),
    1: ("Mostly clear", "clear"),
    2: ("Partly cloudy", "partly"),
    3: ("Overcast", "cloud"),
    45: ("Fog", "fog"),
    48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "rain"),
    53: ("Drizzle", "rain"),
    55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "rain"),
    57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"),
    63: ("Rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"),
    67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"),
    73: ("Snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Light showers", "rain"),
    81: ("Showers", "rain"),
    82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"),
    86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "thunder"),
    96: ("Thunderstorm, hail", "thunder"),
    99: ("Thunderstorm, hail", "thunder"),
}


def _describe(code: int | None) -> dict:
    label, icon = _CODES.get(code, ("Unknown", "cloud"))
    return {"label": label, "icon": icon}


def get_location() -> dict:
    saved = planner_db.get_setting(SETTING_KEY)
    if isinstance(saved, dict) and {"name", "latitude", "longitude"} <= saved.keys():
        return saved
    return DEFAULT_LOCATION


def set_location(name: str, latitude: float, longitude: float) -> dict:
    location = {"name": name.strip(), "latitude": float(latitude), "longitude": float(longitude)}
    planner_db.set_setting(SETTING_KEY, location)
    return location


def search_locations(query: str, limit: int = 6) -> list[dict]:
    """City names and US zip codes both work (Open-Meteo matches postcodes)."""
    query = query.strip()
    if len(query) < 2:
        return []
    resp = httpx.get(
        _GEOCODE_URL,
        params={"name": query, "count": limit, "language": "en", "format": "json"},
        timeout=8,
    )
    resp.raise_for_status()
    out = []
    for r in resp.json().get("results", []):
        parts = [r.get("name"), r.get("admin1")]
        if r.get("country_code") and r["country_code"] != "US":
            parts.append(r.get("country") or r["country_code"])
        out.append(
            {
                "name": ", ".join(p for p in parts if p),
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "detail": r.get("admin2") or "",
            }
        )
    return out


def _fetch(latitude: float, longitude: float) -> dict:
    resp = httpx.get(
        _FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
            "forecast_days": 4,
        },
        timeout=8,
    )
    resp.raise_for_status()
    data = resp.json()
    current, daily = data["current"], data["daily"]
    days = []
    for i, day in enumerate(daily["time"]):
        days.append(
            {
                "date": day,
                "high": round(daily["temperature_2m_max"][i]),
                "low": round(daily["temperature_2m_min"][i]),
                "precip_chance": daily["precipitation_probability_max"][i],
                **_describe(daily["weather_code"][i]),
            }
        )
    return {
        "current": {
            "temp": round(current["temperature_2m"]),
            "feels_like": round(current["apparent_temperature"]),
            "wind_mph": round(current["wind_speed_10m"]),
            "is_day": bool(current.get("is_day", 1)),
            **_describe(current["weather_code"]),
        },
        "days": days,
    }


def get_weather() -> dict:
    location = get_location()
    key = (location["latitude"], location["longitude"])
    cached = _cache.get(key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return {"location": location, **cached[1], "stale": False}
    try:
        forecast = _fetch(*key)
    except Exception:
        # Upstream hiccup: a slightly old forecast beats an empty card.
        if cached:
            return {"location": location, **cached[1], "stale": True}
        raise
    _cache[key] = (now, forecast)
    return {"location": location, **forecast, "stale": False}
