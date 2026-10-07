"""Weather downloads and persistent cache. No GUI or third-party dependencies."""
from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

LOG = logging.getLogger(__name__)


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def location_key(config: dict) -> list:
    return [float(config["latitude"]), float(config["longitude"]), config["timezone"]]


def forecast_url(config: dict) -> str:
    parameters = {
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "timezone": config["timezone"],
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
        "hourly": "temperature_2m,precipitation_probability",
        "forecast_hours": 12,
        "forecast_days": 4,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_probability_max",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
    }
    return "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(parameters)


def validate_forecast(value: object) -> dict:
    if not isinstance(value, dict) or value.get("error"):
        raise ValueError("Respuesta meteorológica inválida")
    current = value.get("current")
    hourly = value.get("hourly")
    if not isinstance(current, dict) or not isinstance(current.get("time"), str):
        raise ValueError("Faltan datos actuales")
    if not isinstance(hourly, dict):
        raise ValueError("Falta el pronóstico horario")
    times = hourly.get("time")
    if not isinstance(times, list) or not times or not all(isinstance(t, str) for t in times):
        raise ValueError("Horas de pronóstico inválidas")
    for name in ("temperature_2m", "precipitation_probability"):
        values = hourly.get(name)
        if not isinstance(values, list) or len(values) != len(times):
            raise ValueError("Serie horaria incompleta")
        if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)) for v in values):
            raise ValueError("Valor horario inválido")
    for name in ("temperature_2m", "apparent_temperature", "weather_code", "wind_speed_10m", "is_day"):
        v = current.get(name)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
            raise ValueError("Valor meteorológico inválido")
    if "daily" in value:
        daily = value["daily"]
        if not isinstance(daily, dict) or not isinstance(daily.get("time"), list) or not daily["time"]:
            raise ValueError("Pronóstico diario inválido")
        dates = daily["time"]
        if not all(isinstance(day, str) for day in dates):
            raise ValueError("Fechas de pronóstico inválidas")
        for name in ("weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max", "sunrise", "sunset"):
            values = daily.get(name)
            if not isinstance(values, list) or len(values) != len(dates):
                raise ValueError("Serie diaria incompleta")
            if name in ("sunrise", "sunset"):
                if any(v is not None and not isinstance(v, str) for v in values):
                    raise ValueError("Hora solar inválida")
            elif any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)) for v in values):
                raise ValueError("Valor diario inválido")
    return value


def read_cache(config: dict, directory: Path) -> list[dict]:
    """A cache from another location or image source is never reused."""
    found = []
    try:
        entry = json.loads((directory / "weather.json").read_text(encoding="utf-8"))
        if entry["location"] == location_key(config):
            forecast = validate_forecast(entry["forecast"])
            found.append({"kind": "weather", "forecast": forecast, "fetched_at": float(entry["fetched_at"])})
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        entry = json.loads((directory / "satellite.json").read_text(encoding="utf-8"))
        image = (directory / "satellite.jpg").read_bytes()
        if entry["url"] == config["satellite_url"] and image.startswith(b"\xff\xd8") and len(image) < 2_000_000:
            found.append({"kind": "satellite", "image": image, "fetched_at": float(entry["fetched_at"])})
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return found


def download(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "PiClima/1.0 (personal weather display)", "Accept": "application/json,image/jpeg,*/*"})
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("La descarga excede el tamaño previsto")
    return payload


def fetch_weather(config: dict, directory: Path) -> dict:
    forecast = validate_forecast(json.loads(download(forecast_url(config), 200_000)))
    fetched_at = time.time()
    entry = {"location": location_key(config), "fetched_at": fetched_at, "forecast": forecast}
    try:
        atomic_write(directory / "weather.json", json.dumps(entry, ensure_ascii=False).encode("utf-8"))
    except OSError as exc:
        LOG.warning("No se pudo guardar la caché de clima: %s", exc)
    return {"kind": "weather", "forecast": forecast, "fetched_at": fetched_at}


def fetch_satellite(config: dict) -> dict:
    image = download(config["satellite_url"], 2_000_000)
    if not image.startswith(b"\xff\xd8"):
        raise ValueError("NOAA no devolvió una imagen JPEG")
    return {"kind": "satellite", "image": image, "fetched_at": time.time()}


def save_satellite(config: dict, directory: Path, event: dict) -> None:
    """Called only after the GUI has successfully decoded the JPEG."""
    try:
        atomic_write(directory / "satellite.jpg", event["image"])
        metadata = {"url": config["satellite_url"], "fetched_at": event["fetched_at"]}
        atomic_write(directory / "satellite.json", json.dumps(metadata).encode("utf-8"))
    except OSError as exc:
        LOG.warning("No se pudo guardar la caché de satélite: %s", exc)


def run_downloads(config: dict, directory: Path, events, stop) -> None:
    from satellite_data import fetch_history, history_source
    from geo_satellite import fetch_history as fetch_geographic_history, supported

    satellite_action = (lambda: fetch_history(config, directory, stop)) if history_source(config) else (lambda: fetch_satellite(config))
    if supported(config):
        satellite_action = lambda: fetch_geographic_history(config, directory, stop)
    tasks = {
        "weather": (float(config["weather_refresh_seconds"]), lambda: fetch_weather(config, directory)),
        "satellite": (float(config["satellite_refresh_seconds"]), satellite_action),
    }
    due = {kind: 0.0 for kind in tasks}
    failures = {kind: 0 for kind in tasks}
    while not stop.is_set():
        for kind, (interval, action) in tasks.items():
            if stop.is_set():
                return
            if time.monotonic() < due[kind]:
                continue
            try:
                result = action()
                events.put(result)
                if result.get("warning"):
                    failures[kind] += 1
                    delay = min(interval, 30 * 2 ** min(failures[kind] - 1, 5))
                else:
                    failures[kind] = 0
                    delay = interval
                due[kind] = time.monotonic() + delay
            except Exception as exc:
                LOG.warning("Descarga de %s: %s", kind, exc)
                events.put({"kind": kind, "error": str(exc)})
                failures[kind] += 1
                delay = min(interval, 30 * 2 ** min(failures[kind] - 1, 5))
                due[kind] = time.monotonic() + delay
        wait = max(0.1, min(due.values()) - time.monotonic())
        stop.wait(min(wait, 1.0))
