"""Deterministic test fixtures and a headless SDL environment."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

PROJECT = Path(os.environ.get("PI_CLIMA_TEST_PROJECT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(PROJECT))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

CONFIG = {
    "city": "Xalapa, Veracruz", "latitude": 19.53124, "longitude": -96.91589,
    "timezone": "America/Mexico_City", "weather_refresh_seconds": 900,
    "satellite_refresh_seconds": 600, "page_seconds": 30,
    "rain_alert_probability": 60,
    "satellite_url": "https://cdn.star.nesdis.noaa.gov/GOES19/ABI/SECTOR/mex/GEOCOLOR/500x500.jpg",
}

FORECAST = {
    "timezone": "America/Mexico_City",
    "current": {"time": "2026-10-06T14:00", "temperature_2m": 22,
                "apparent_temperature": 23, "weather_code": 2,
                "wind_speed_10m": 12, "is_day": 1},
    "hourly": {
        "time": [(datetime(2026, 10, 6, 14) + timedelta(hours=i)).isoformat(timespec="minutes")
                 for i in range(12)],
        "temperature_2m": [22, 23, 24, 24, 23, 22, 21, 20, 19, 18, 18, 17],
        "precipitation_probability": [20, 30, 40, 50, 70, 65, 60, 50, 40, 30, 20, 10],
    },
}


class FixedDatetime(datetime):
    """A stable instant for the application's routing test."""
    @classmethod
    def now(cls, tz=None):
        instant = cls(2026, 10, 7, 2, 30, tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)
