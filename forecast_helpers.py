"""Small, timezone-aware views of Open-Meteo forecast data."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def _probability(value: object) -> int | float | None:
    value = _number(value)
    return value if value is not None and 0 <= value <= 100 else None


def _section(forecast: dict, name: str) -> dict:
    value = forecast.get(name) if isinstance(forecast, dict) else None
    return value if isinstance(value, dict) else {}


def _array(section: dict, name: str) -> list | tuple:
    value = section.get(name)
    return value if isinstance(value, (list, tuple)) else []


def _at(section: dict, name: str, index: int) -> object:
    values = _array(section, name)
    return values[index] if index < len(values) else None


def _zone(forecast: dict, now: datetime) -> tzinfo | None:
    name = forecast.get("timezone") if isinstance(forecast, dict) else None
    if isinstance(name, str) and name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return now.tzinfo


def _local_now(now: datetime, zone: tzinfo | None) -> datetime:
    if zone is None:
        return now
    return now.replace(tzinfo=zone) if now.tzinfo is None else now.astimezone(zone)


def _moment(value: object, zone: tzinfo | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
        if zone is None:
            return result.replace(tzinfo=None)
        return result.replace(tzinfo=zone) if result.tzinfo is None else result.astimezone(zone)
    except (ValueError, OverflowError):
        return None


def future_hourly(forecast: dict, now: datetime, max_hours: int | float = 12) -> list[dict]:
    """Return available periods from this hour, excluding the horizon's end."""
    hours = _number(max_hours)
    if hours is None or hours <= 0:
        return []
    zone = _zone(forecast, now)
    start = _local_now(now, zone).replace(minute=0, second=0, microsecond=0)
    try:
        end = start + timedelta(hours=hours)
    except OverflowError:
        return []
    hourly = _section(forecast, "hourly")
    rows = []
    for index, value in enumerate(_array(hourly, "time")):
        moment = _moment(value, zone)
        if moment is not None and start <= moment < end:
            rows.append({
                "time": moment,
                "temperature": _number(_at(hourly, "temperature_2m", index)),
                "probability": _probability(_at(hourly, "precipitation_probability", index)),
            })
    return sorted(rows, key=lambda row: row["time"])


def compute_rain_alert(forecast: dict, now: datetime, threshold: int | float = 60, hours: int | float = 6) -> dict | None:
    """Describe forecast probabilities, never a guarantee of imminent rain.

    Open-Meteo assigns each probability to the hour preceding its timestamp.
    Finished periods are excluded, and a current period starts at ``now``.
    """
    limit = _probability(threshold)
    if limit is None:
        raise ValueError("El umbral de lluvia debe ser un número entre 0 y 100.")
    horizon = _number(hours)
    if horizon is None or horizon <= 0:
        return None
    local_now = _local_now(now, _zone(forecast, now))
    try:
        horizon_end = local_now + timedelta(hours=horizon)
    except OverflowError:
        return None
    qualifying = [
        row for row in future_hourly(forecast, now, max_hours=horizon + 1)
        if local_now < row["time"] <= horizon_end
        and row["probability"] is not None and row["probability"] >= limit
    ]
    if not qualifying:
        return None
    intervals = [{
        "start": max(row["time"] - timedelta(hours=1), local_now),
        "end": row["time"],
        "probability": row["probability"],
    } for row in qualifying]
    return {
        "probability": max(row["probability"] for row in qualifying),
        "start": intervals[0]["start"],
        "end": intervals[-1]["end"],
        "intervals": intervals,
    }


def daily_rows(forecast: dict, now: datetime, include_today: bool = True) -> list[dict]:
    """Return remaining local days; absent or invalid fields stay unknown."""
    zone = _zone(forecast, now)
    today = _local_now(now, zone).date()
    daily = _section(forecast, "daily")
    rows = []
    for index, value in enumerate(_array(daily, "time")):
        if not isinstance(value, str):
            continue
        try:
            day = date.fromisoformat(value)
        except ValueError:
            continue
        if day < today or (day == today and not include_today):
            continue
        rows.append({
            "date": day,
            "max": _number(_at(daily, "temperature_2m_max", index)),
            "min": _number(_at(daily, "temperature_2m_min", index)),
            "sunrise": _moment(_at(daily, "sunrise", index), zone),
            "sunset": _moment(_at(daily, "sunset", index), zone),
            "code": _number(_at(daily, "weather_code", index)),
            "probability": _probability(_at(daily, "precipitation_probability_max", index)),
        })
    return sorted(rows, key=lambda row: row["date"])
