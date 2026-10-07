"""Fetch one small geographic patch for a paused satellite frame.

The caller debounces requests and decodes the JPEG on the GUI thread.  This
module keeps no image history: one cache entry bounds disk and memory use.
"""
from __future__ import annotations

from hashlib import sha256
import json
import logging
import math
from pathlib import Path
import time
from urllib.parse import urlencode, urlparse

from data import atomic_write, download
from geo_satellite import BBOX, SERVICE, LIMIT, frame_time, parse_catalog, valid_extent

LOG = logging.getLogger(__name__)
MAX_SIDE = 800


def _cancelled(stop) -> None:
    if stop is not None and stop.is_set():
        raise InterruptedError("Consulta de detalle cancelada")


def _request(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("Solicitud de detalle inválida")
    token = request.get("request_token")
    if isinstance(token, bool) or not isinstance(token, int) or token < 0:
        raise ValueError("Identificador de detalle inválido")
    key = request.get("key")
    captured = frame_time(key)
    provided = request.get("captured_at")
    if (isinstance(provided, bool) or not isinstance(provided, (float, int))
            or not math.isfinite(provided) or abs(provided - captured) > 0.001):
        raise ValueError("La fecha del detalle no coincide con el cuadro")
    bounds = request.get("extent")
    if not valid_extent(bounds):
        raise ValueError("Extensión del detalle inválida")
    bounds = [round(float(value), 6) for value in bounds]
    if (not valid_extent(bounds) or bounds[0] < BBOX[0] or bounds[1] < BBOX[1]
            or bounds[2] > BBOX[2] or bounds[3] > BBOX[3]):
        raise ValueError("El detalle está fuera de la imagen de México")
    span_x, span_y = bounds[2] - bounds[0], bounds[3] - bounds[1]
    scale = MAX_SIDE / max(span_x, span_y)
    size = [max(1, round(span_x * scale)), max(1, round(span_y * scale))]
    # Near-degenerate extents cannot produce a useful geographic image.
    if min(size) < 32:
        raise ValueError("La proporción del detalle es inválida")
    return {"request_token": token, "key": key, "captured_at": captured,
            "extent": bounds, "size": size}


def _json(url: str) -> dict:
    response = json.loads(download(url, 300_000))
    if not isinstance(response, dict) or response.get("error"):
        raise ValueError("NOAA no devolvió metadatos de detalle válidos")
    return response


def _jpeg_size(payload: bytes) -> tuple[int, int] | None:
    """Read JPEG's frame dimensions without allocating a decoded bitmap."""
    if not isinstance(payload, bytes) or not 4 <= len(payload) <= LIMIT:
        return None
    if not payload.startswith(b"\xff\xd8") or b"\xff\xd9" not in payload:
        return None
    position = 2
    frame_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while position < len(payload):
        if payload[position] != 0xFF:
            return None
        while position < len(payload) and payload[position] == 0xFF:
            position += 1
        if position >= len(payload):
            return None
        marker = payload[position]
        position += 1
        if marker in (0xD9, 0xDA):
            return None
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            continue
        if position + 2 > len(payload):
            return None
        length = int.from_bytes(payload[position:position + 2], "big")
        if length < 2 or position + length > len(payload):
            return None
        if marker in frame_markers:
            if length < 8:
                return None
            height = int.from_bytes(payload[position + 3:position + 5], "big")
            width = int.from_bytes(payload[position + 5:position + 7], "big")
            return (width, height) if width > 0 and height > 0 else None
        position += length
    return None


def _directory(directory: Path) -> Path:
    base = Path(directory).resolve()
    target = (base / "satellite-detail" / sha256(SERVICE.encode()).hexdigest()[:16]).resolve()
    if not target.is_relative_to(base):
        raise ValueError("La caché de detalle está fuera del directorio previsto")
    return target


def _path(folder: Path, name: str) -> Path:
    path = folder / name
    if path.is_symlink() or path.resolve().parent != folder:
        raise ValueError("Ruta de caché de detalle inválida")
    return path


def _identity(request: dict) -> dict:
    return {key: request[key] for key in ("key", "captured_at", "extent", "size")}


def read_detail(request: dict, directory: Path) -> dict | None:
    wanted = _request(request)
    try:
        folder = _directory(directory)
        manifest_path = _path(folder, "detail.json")
        if manifest_path.stat().st_size > 20_000:
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stamp = manifest.get("fetched_at")
        if (manifest.get("version") != 1 or manifest.get("source") != SERVICE
                or manifest.get("identity") != _identity(wanted)
                or isinstance(stamp, bool) or not isinstance(stamp, (float, int))
                or not math.isfinite(stamp) or stamp <= 0):
            return None
        with _path(folder, "detail.jpg").open("rb") as handle:
            image = handle.read(LIMIT + 1)
        if (_jpeg_size(image) != tuple(wanted["size"])
                or sha256(image).hexdigest() != manifest.get("sha256")):
            return None
        frame = {key: wanted[key] for key in ("key", "captured_at", "extent")}
        frame.update(crs="EPSG:4326", source="NOAA", image=image)
        return {"kind": "satellite_detail", "request_token": wanted["request_token"],
                "frames": [frame], "fetched_at": stamp}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _save(request: dict, event: dict, directory: Path) -> None:
    folder = _directory(directory)
    image = event["frames"][0]["image"]
    manifest = {"version": 1, "source": SERVICE, "identity": _identity(request),
                "fetched_at": event["fetched_at"], "sha256": sha256(image).hexdigest()}
    # The hash prevents reading an old manifest with a newly replaced image.
    atomic_write(_path(folder, "detail.jpg"), image)
    atomic_write(_path(folder, "detail.json"), json.dumps(manifest).encode("utf-8"))


def fetch_detail(request: dict, directory: Path, stop=None) -> dict:
    """Return one matching frame or raise; never substitute another scene."""
    wanted = _request(request)
    _cancelled(stop)
    cached = read_detail(wanted, directory)
    if cached is not None:
        return cached
    stamp = int(wanted["captured_at"] * 1000)
    parameters = {"f": "json", "where": "category=1", "outFields": "objectid,start_time",
                  "returnGeometry": "false", "orderByFields": "start_time DESC",
                  "resultRecordCount": 8, "time": f"{stamp},{stamp + 59_999}"}
    catalog = _json(SERVICE + "/query?" + urlencode(parameters))
    if not isinstance(catalog.get("features"), list):
        raise ValueError("El catálogo de detalle NOAA es inválido")
    matches = [row for row in parse_catalog(catalog, 8) if row["key"] == wanted["key"]]
    if not matches:
        raise ValueError("La captura seleccionada ya no está disponible para detalle")
    record = matches[-1]
    _cancelled(stop)
    rule = {"mosaicMethod": "esriMosaicLockRaster", "lockRasterIds": [record["objectid"]],
            "mosaicOperation": "MT_FIRST"}
    parameters = {"f": "json", "bbox": ",".join(str(v) for v in wanted["extent"]),
                  "bboxSR": 4326, "imageSR": 4326,
                  "size": ",".join(str(v) for v in wanted["size"]),
                  "adjustAspectRatio": "false", "format": "jpg", "compressionQuality": 85,
                  "mosaicRule": json.dumps(rule, separators=(",", ":")), "time": stamp}
    metadata = _json(SERVICE + "/exportImage?" + urlencode(parameters))
    extent = metadata.get("extent", {})
    if not isinstance(extent, dict):
        raise ValueError("La extensión del detalle NOAA es inválida")
    bounds = [extent.get(name) for name in ("xmin", "ymin", "xmax", "ymax")]
    reference = extent.get("spatialReference", {})
    if not isinstance(reference, dict):
        raise ValueError("La referencia del detalle NOAA es inválida")
    if (metadata.get("width") != wanted["size"][0] or metadata.get("height") != wanted["size"][1]
            or not valid_extent(bounds) or reference.get("latestWkid", reference.get("wkid")) != 4326
            or any(abs(a - b) > 1e-6 for a, b in zip(bounds, wanted["extent"]))):
        raise ValueError("El detalle NOAA no coincide con la extensión solicitada")
    href = metadata.get("href", "")
    parsed = urlparse(href)
    if (parsed.scheme != "https" or parsed.hostname != "satellitemaps.nesdis.noaa.gov"
            or parsed.username or parsed.password):
        raise ValueError("Dirección de detalle NOAA inválida")
    _cancelled(stop)
    image = download(href, LIMIT)
    if _jpeg_size(image) != tuple(wanted["size"]):
        raise ValueError("NOAA no devolvió un JPEG de detalle completo y acotado")
    _cancelled(stop)
    frame = {**record, "extent": wanted["extent"], "crs": "EPSG:4326", "source": "NOAA", "image": image}
    event = {"kind": "satellite_detail", "request_token": wanted["request_token"],
             "frames": [frame], "fetched_at": time.time()}
    try:
        _save(wanted, event, directory)
    except (OSError, ValueError) as exc:
        LOG.warning("No se guardó el detalle satelital: %s", exc)
    return event
