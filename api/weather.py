"""
api/weather.py — this week's weather for the Home page, from Open-Meteo.

Open-Meteo is free and keyless (https://open-meteo.com). One request returns the current
conditions plus daily highs/lows/codes for the Monday–Sunday week, past days included.
Cached in-process for 30 minutes. The location defaults to Denver (the app already pins
"today" to America/Denver, see api/store.today_local); override with ONS_LAT / ONS_LON /
ONS_PLACE in the environment.

Conditions are reduced to the six states the This Week pixel scene draws:
sun · partly · cloudy · wind · rain · snow.
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from typing import Any

import httpx

LAT = float(os.getenv("ONS_LAT", "39.7392"))
LON = float(os.getenv("ONS_LON", "-104.9903"))
PLACE = os.getenv("ONS_PLACE", "Denver")
TZ = "America/Denver"
URL = "https://api.open-meteo.com/v1/forecast"
TTL = 30 * 60
WINDY_GUST_MPH = 30.0

_cache: dict[str, tuple[float, Any]] = {}


def condition(code: int | None, gust: float | None = None) -> str:
    """WMO weather code (+ gusts) → one of the scene's six states."""
    if code is None:
        return "cloudy"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if 51 <= code <= 67 or 80 <= code <= 82 or code >= 95:
        return "rain"
    if gust is not None and gust >= WINDY_GUST_MPH:
        return "wind"
    if code in (0, 1):
        return "sun"
    if code == 2:
        return "partly"
    return "cloudy"  # 3 overcast, 45/48 fog


LABELS = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Showers", 81: "Showers",
    82: "Heavy showers", 85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorms", 96: "Thunderstorms", 99: "Thunderstorms",
}


def _label(code: int | None, gust: float | None, snow_in: float | None) -> str:
    base = LABELS.get(code if code is not None else -1, "—")
    if snow_in and snow_in >= 0.5:
        base = f"{base}, {snow_in:.0f} in." if snow_in >= 1 else f"{base}, <1 in."
    if gust is not None and gust >= WINDY_GUST_MPH:
        base = f"{base}, gusts {gust:.0f}"
    return base


async def week_weather(today: date) -> dict:
    """Current conditions + each day of today's Monday–Sunday week."""
    key = f"{today.isoformat()}:{LAT}:{LON}"
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]

    monday = today - timedelta(days=today.weekday())
    params = {
        "latitude": LAT, "longitude": LON, "timezone": TZ,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum,wind_gusts_10m_max",
        "current": "temperature_2m,weather_code,wind_gusts_10m",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch",
        "past_days": today.weekday(), "forecast_days": 7 - today.weekday(),
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(URL, params=params, timeout=10)
        r.raise_for_status()
        raw = r.json()

    d = raw.get("daily") or {}
    days = []
    for i, iso in enumerate(d.get("time") or []):
        day = date.fromisoformat(iso)
        if not (monday <= day <= monday + timedelta(days=6)):
            continue
        code = (d.get("weather_code") or [None])[i]
        gust = (d.get("wind_gusts_10m_max") or [None])[i]
        snow = (d.get("snowfall_sum") or [None])[i]
        days.append({
            "date": iso,
            "condition": condition(code, gust),
            "label": _label(code, gust, snow),
            "high_f": round((d.get("temperature_2m_max") or [None])[i] or 0),
            "low_f": round((d.get("temperature_2m_min") or [None])[i] or 0),
            "precip_in": (d.get("precipitation_sum") or [None])[i],
            "snow_in": snow,
            "gust_mph": gust,
            "past": day < today,
        })

    cur = raw.get("current") or {}
    out = {
        "place": PLACE,
        "today": today.isoformat(),
        "current": {
            "temp_f": round(cur["temperature_2m"]) if cur.get("temperature_2m") is not None else None,
            "condition": condition(cur.get("weather_code"), cur.get("wind_gusts_10m")),
            "label": LABELS.get(cur.get("weather_code") if cur.get("weather_code") is not None else -1, "—"),
            "as_of": cur.get("time"),
        },
        "days": days,
        "source": "Open-Meteo",
    }
    _cache[key] = (time.monotonic() + TTL, out)
    return out
