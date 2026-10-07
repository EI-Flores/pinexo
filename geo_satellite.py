"""NOAA GeoColor history exported with an explicit WGS84 geographic extent."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import math
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlparse

from data import atomic_write, download
from satellite_data import frame_count, history_source

LOG = logging.getLogger(__name__)
SERVICE = "https://satellitemaps.nesdis.noaa.gov/arcgis/rest/services/ABIGC_Last_24hr/ImageServer"
# A square extent keeps equal angular scales; covers all Mexican entities.
BBOX = (-121.0, 6.0, -85.0, 42.0)
SIZE = 1000
LIMIT = 2_000_000
KEY = re.compile(r"[0-9]{11}")

def supported(config: dict) -> bool:
    return history_source(config) is not None and config.get("satellite_geography", True) is not False

def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)

def valid_extent(value) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 4 and all(_finite(v) for v in value)
            and -180 <= value[0] < value[2] <= 180 and -90 <= value[1] < value[3] <= 90)

def frame_time(key: str) -> float:
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise ValueError("Clave satelital inválida")
    dt = datetime.strptime(key, "%Y%j%H%M").replace(tzinfo=timezone.utc)
    if dt.strftime("%Y%j%H%M") != key:
        raise ValueError("Fecha satelital inválida")
    return dt.timestamp()

def _jpeg(payload: bytes) -> bool:
    # ArcGIS may append padding after JPEG's end-of-image marker.
    return 4 <= len(payload) <= LIMIT and payload.startswith(b"\xff\xd8") and b"\xff\xd9" in payload

def _json(url: str) -> dict:
    response = json.loads(download(url, 300_000))
    if not isinstance(response, dict) or response.get("error"):
        raise ValueError("NOAA no devolvió metadatos válidos")
    return response

def parse_catalog(value: dict, count: int) -> list[dict]:
    frames = {}
    for feature in value.get("features", []):
        try:
            attrs = {key.lower(): v for key, v in feature["attributes"].items()}
            oid, stamp = attrs["objectid"], attrs["start_time"]
            if not _finite(oid) or int(oid) != oid or oid < 0 or not _finite(stamp) or stamp <= 0:
                continue
            dt = datetime.fromtimestamp(stamp / 1000, timezone.utc)
            key = dt.strftime("%Y%j%H%M")
            captured_at = frame_time(key)
            frames[key] = {"key": key, "captured_at": captured_at, "objectid": int(oid)}
        except (ValueError, OSError, OverflowError, KeyError, TypeError, AttributeError):
            continue
    return sorted(frames.values(), key=lambda row: row["captured_at"])[-count:]

def export_frame(record: dict) -> dict:
    rule = {"mosaicMethod": "esriMosaicLockRaster", "lockRasterIds": [record["objectid"]], "mosaicOperation": "MT_FIRST"}
    parameters = {"f": "json", "bbox": ",".join(str(v) for v in BBOX), "bboxSR": 4326,
                  "imageSR": 4326, "size": f"{SIZE},{SIZE}", "adjustAspectRatio": "false",
                  "format": "jpg", "compressionQuality": 80, "mosaicRule": json.dumps(rule, separators=(",", ":")),
                  "time": int(record["captured_at"] * 1000)}
    metadata = _json(SERVICE + "/exportImage?" + urlencode(parameters))
    extent = metadata.get("extent", {})
    bounds = [extent.get(name) for name in ("xmin", "ymin", "xmax", "ymax")]
    reference = extent.get("spatialReference", {})
    if (metadata.get("width") != SIZE or metadata.get("height") != SIZE or not valid_extent(bounds)
            or reference.get("latestWkid", reference.get("wkid")) != 4326
            or any(abs(a - b) > 1e-6 for a, b in zip(bounds, BBOX))):
        raise ValueError("La imagen NOAA no coincide con la extensión geográfica solicitada")
    href = metadata.get("href", "")
    parsed = urlparse(href)
    if parsed.scheme != "https" or parsed.hostname != "satellitemaps.nesdis.noaa.gov" or parsed.username or parsed.password:
        raise ValueError("Dirección de imagen NOAA inválida")
    image = download(href, LIMIT)
    if not _jpeg(image):
        raise ValueError("NOAA no devolvió un JPEG completo")
    return {**record, "extent": bounds, "crs": "EPSG:4326", "source": "NOAA", "image": image}

def _directory(directory: Path) -> Path:
    base = directory.resolve()
    identity = json.dumps([SERVICE, BBOX, SIZE]).encode("utf-8")
    target = (base / "satellite-geographic" / sha256(identity).hexdigest()[:16]).resolve()
    if not target.is_relative_to(base):
        raise ValueError("La caché está fuera del directorio previsto")
    return target

def read_history(config: dict, directory: Path) -> dict | None:
    if not supported(config):
        return None
    try:
        folder = _directory(directory)
        path = folder / "manifest.json"
        if path.stat().st_size > 50_000:
            return None
        manifest = json.loads(path.read_text(encoding="utf-8"))
        records = manifest["frames"]
        stamp = manifest["fetched_at"]
        if (manifest.get("source") != SERVICE or manifest.get("bbox") != list(BBOX)
                or manifest.get("version") != 1 or not _finite(stamp) or stamp <= 0
                or not isinstance(records, list) or not 1 <= len(records) <= 12):
            return None
        frames = {}
        for record in records:
            try:
                key = record["key"]
                captured = frame_time(key)
                if (record.get("crs") != "EPSG:4326" or not valid_extent(record.get("extent"))
                        or any(abs(a - b) > 1e-6 for a, b in zip(record["extent"], BBOX))):
                    continue
                image_path = folder / (key + ".jpg")
                if image_path.is_symlink() or not image_path.resolve().is_relative_to(folder):
                    continue
                with image_path.open("rb") as handle:
                    image = handle.read(LIMIT + 1)
                if _jpeg(image):
                    frames[key] = {**record, "captured_at": captured, "source": "NOAA", "image": image}
            except (KeyError, ValueError, TypeError, OSError):
                continue
        ordered = sorted(frames.values(), key=lambda row: row["captured_at"])[-frame_count(config):]
        if not ordered:
            return None
        event = {"kind": "satellite_history", "frames": ordered, "fetched_at": stamp}
        warning = manifest.get("warning")
        if isinstance(warning, str) and warning:
            event["warning"] = warning[:300]
        if len(ordered) < min(len(records), frame_count(config)):
            event["warning"] = "Historial guardado incompleto"
        return event
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None

def _save(directory: Path, event: dict) -> None:
    folder = _directory(directory)
    records = []
    for frame in event["frames"]:
        path = folder / (frame["key"] + ".jpg")
        if not path.exists() or path.is_symlink():
            atomic_write(path, frame["image"])
        else:
            with path.open("rb") as handle:
                existing = handle.read(LIMIT + 1)
            if existing != frame["image"]:
                atomic_write(path, frame["image"])
        records.append({key: frame[key] for key in ("key", "captured_at", "extent", "crs")})
    manifest = {"version": 1, "source": SERVICE, "bbox": list(BBOX), "frames": records,
                "fetched_at": event["fetched_at"], "warning": event.get("warning")}
    atomic_write(folder / "manifest.json", json.dumps(manifest).encode("utf-8"))
    keep = {row["key"] + ".jpg" for row in records}
    # Delete only own timestamp images, within the resolved cache, after commit.
    for path in folder.iterdir():
        if (path.name not in keep and re.fullmatch(r"[0-9]{11}\.jpg", path.name)
                and not path.is_symlink() and path.is_file() and path.resolve().parent == folder):
            try:
                path.unlink()
            except OSError as exc:
                LOG.warning("No se retiró un cuadro antiguo: %s", exc)

def fetch_history(config: dict, directory: Path, stop=None) -> dict:
    cached = read_history(config, directory)
    if stop is not None and stop.is_set():
        raise InterruptedError("Consulta cancelada")
    parameters = {"f": "json", "where": "category=1", "outFields": "objectid,start_time,end_time,name",
                  "returnGeometry": "false", "orderByFields": "start_time DESC", "resultRecordCount": 24}
    try:
        wanted = parse_catalog(_json(SERVICE + "/query?" + urlencode(parameters)), frame_count(config))
        if not wanted:
            raise ValueError("NOAA no publicó cuadros disponibles")
    except Exception:
        if not cached:
            raise
        return dict(cached, warning="No se actualizó el satélite · cuadros guardados")
    available = {row["key"]: row for row in (cached or {}).get("frames", [])}
    failed = False
    for record in reversed(wanted):
        if stop is not None and stop.is_set():
            failed = True
            break
        if record["key"] in available:
            continue
        try:
            available[record["key"]] = export_frame(record)
        except Exception as exc:
            failed = True
            LOG.warning("Cuadro NOAA geográfico %s: %s", record["key"], exc)
    if not available:
        raise ValueError("No se pudo descargar ningún cuadro geográfico")
    frames = sorted(available.values(), key=lambda row: row["captured_at"])[-frame_count(config):]
    event = {"kind": "satellite_history", "frames": frames, "fetched_at": time.time()}
    if failed or wanted[-1]["key"] not in available:
        event["warning"] = "Historial incompleto · cuadros disponibles"
    try:
        _save(directory, event)
    except (OSError, ValueError) as exc:
        LOG.warning("No se guardó la caché geográfica: %s", exc)
        event.setdefault("warning", "Imágenes descargadas · caché no guardada")
    return event
