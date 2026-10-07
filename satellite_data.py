"""Bounded NOAA GeoColor history downloads and cache; no display dependencies.

The public directory lists observation times as YYYYDDDHHMM (UTC).  History
always uses the 1000-pixel source so that a crop has more detail than the LCD.
Call ``fetch_history`` from the download worker, never from the display loop.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import logging
import math
from pathlib import Path
import re
import time

from data import atomic_write, download

LOG = logging.getLogger(__name__)
SOURCE = "https://cdn.star.nesdis.noaa.gov/GOES19/ABI/SECTOR/mex/GEOCOLOR/"
DEFAULT_COUNT = 8
MAX_COUNT = 12
IMAGE_LIMIT = 2_000_000
LISTING_LIMIT = 3_000_000
NAME = re.compile(r"([0-9]{11})_GOES19-ABI-mex-GEOCOLOR-1000x1000\.jpg")
KEY = re.compile(r"[0-9]{11}")
ALLOWED_IMAGES = {SOURCE + size + ".jpg" for size in ("250x250", "500x500", "1000x1000", "2000x2000", "4000x4000")}


def history_source(config: dict) -> str | None:
    """Return the supported directory, or None for a custom single-image URL."""
    return SOURCE if config.get("satellite_url") in ALLOWED_IMAGES else None


def frame_count(config: dict) -> int:
    value = config.get("satellite_frame_count", DEFAULT_COUNT)
    if isinstance(value, bool):
        return DEFAULT_COUNT
    try:
        return max(2, min(MAX_COUNT, int(value)))
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_COUNT


def _captured_at(key: str) -> float:
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise ValueError("Identificador satelital inválido")
    observed = datetime.strptime(key, "%Y%j%H%M").replace(tzinfo=timezone.utc)
    # strptime can roll day 366 into the following year for a non-leap year.
    if observed.strftime("%Y%j%H%M") != key:
        raise ValueError("Fecha satelital inválida")
    return observed.timestamp()


def _image_valid(payload: bytes) -> bool:
    return 4 <= len(payload) <= IMAGE_LIMIT and payload.startswith(b"\xff\xd8") and payload.endswith(b"\xff\xd9")


class _Listing(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.frames: dict[str, dict] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            # Only the exact relative JPEG filename is accepted. No arbitrary
            # hosts, paths, query strings, or filenames from the index are used.
            match = NAME.fullmatch(value or "") if name.lower() == "href" else None
            if match:
                key = match.group(1)
                try:
                    captured_at = _captured_at(key)
                except ValueError:
                    continue
                self.frames[key] = {"key": key, "captured_at": captured_at, "url": SOURCE + value}


def parse_listing(payload: bytes, count: int = DEFAULT_COUNT) -> list[dict]:
    if len(payload) > LISTING_LIMIT:
        raise ValueError("El índice satelital excede el tamaño previsto")
    parser = _Listing()
    parser.feed(payload.decode("utf-8", errors="replace"))
    parser.close()
    # Sorting the UTC observation times handles day/year boundaries correctly.
    frames = sorted(parser.frames.values(), key=lambda item: item["captured_at"])
    return frames[-max(2, min(MAX_COUNT, count)):]


def _cache_directory(directory: Path, source: str) -> Path:
    base = Path(directory).resolve()
    target = (base / "satellite-history" / sha256(source.encode("utf-8")).hexdigest()[:16]).resolve()
    if not target.is_relative_to(base):
        raise ValueError("La caché satelital está fuera del directorio previsto")
    return target


def read_history(config: dict, directory: Path) -> dict | None:
    """Load only complete JPEG files named by a valid, matching-source manifest."""
    source = history_source(config)
    if source is None:
        return None
    try:
        cache = _cache_directory(directory, source)
        manifest = cache / "manifest.json"
        if manifest.stat().st_size > 50_000:
            return None
        entry = json.loads(manifest.read_text(encoding="utf-8"))
        if entry.get("source") != source or entry.get("version") != 1:
            return None
        records = entry["frames"]
        if not isinstance(records, list) or not 1 <= len(records) <= MAX_COUNT:
            return None
        fetched_at = float(entry["fetched_at"])
        if not math.isfinite(fetched_at) or fetched_at <= 0:
            return None
        frames = []
        for record in records:
            try:
                key = record["key"]
                captured_at = _captured_at(key)
                image_url = source + key + "_GOES19-ABI-mex-GEOCOLOR-1000x1000.jpg"
                if record.get("url") != image_url:
                    continue
                image_path = cache / (key + ".jpg")
                if image_path.is_symlink() or not image_path.resolve().is_relative_to(cache):
                    continue
                with image_path.open("rb") as handle:
                    image = handle.read(IMAGE_LIMIT + 1)
                if _image_valid(image):
                    frames.append({"key": key, "captured_at": captured_at, "image": image, "url": image_url})
            except (OSError, KeyError, TypeError, ValueError):
                continue
        frames = sorted({item["key"]: item for item in frames}.values(), key=lambda item: item["captured_at"])[-frame_count(config):]
        if not frames:
            return None
        event = {"kind": "satellite_history", "frames": frames, "fetched_at": fetched_at}
        latest = entry.get("latest_requested")
        if isinstance(latest, str) and KEY.fullmatch(latest):
            event["latest_requested"] = latest
        warning = entry.get("warning")
        if isinstance(warning, str) and warning:
            event["warning"] = warning[:300]
        if len(frames) < min(len(records), frame_count(config)):
            event["warning"] = "La caché satelital está incompleta; se conservan los cuadros válidos."
        return event
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _save_history(config: dict, directory: Path, source: str, event: dict) -> None:
    cache = _cache_directory(directory, source)
    metadata = {
        "version": 1,
        "source": source,
        "fetched_at": event["fetched_at"],
        "latest_requested": event.get("latest_requested"),
        "frames": [{"key": item["key"], "url": item["url"]} for item in event["frames"]],
    }
    if event.get("warning"):
        metadata["warning"] = event["warning"]
    # Write all frames before replacing the index. If either fails, the previous
    # manifest and its valid frames remain readable; cleanup does not run.
    for item in event["frames"]:
        path = cache / (item["key"] + ".jpg")
        same_image = False
        if not path.is_symlink():
            try:
                with path.open("rb") as handle:
                    same_image = handle.read(IMAGE_LIMIT + 1) == item["image"]
            except OSError:
                pass
        if not same_image:
            atomic_write(path, item["image"])
    atomic_write(cache / "manifest.json", json.dumps(metadata).encode("utf-8"))
    keep = {item["key"] + ".jpg" for item in event["frames"]}
    # The resolved cache was checked above. Only our own exact timestamp JPEG
    # names are pruned, after publishing the successfully written manifest.
    for path in cache.iterdir():
        if path.name in keep or not re.fullmatch(r"[0-9]{11}\.jpg", path.name) or path.is_symlink():
            continue
        if path.is_file() and path.resolve().parent == cache:
            try:
                path.unlink()
            except OSError as exc:
                LOG.warning("No se pudo retirar un cuadro antiguo: %s", exc)


def fetch_history(config: dict, directory: Path, stop=None) -> dict:
    """Download at most 12 recent frames, retaining valid cache on partial failure.

    Returns a satellite_history event. ``warning`` means that the index or some
    requested frames failed, so the UI must not claim a fully successful update.
    ``captured_at`` is the UTC observation time; ``fetched_at`` is the successful
    index check time. A custom source raises ValueError for the caller's existing
    single-image fallback. An empty/cancelled first download raises an exception.
    """
    source = history_source(config)
    if source is None:
        raise ValueError("Esta fuente personalizada no ofrece el historial NOAA de México")
    cached = read_history(config, directory)
    count = frame_count(config)
    available = {item["key"]: item for item in (cached or {}).get("frames", [])}
    if stop is not None and stop.is_set():
        raise InterruptedError("Descarga satelital cancelada")
    try:
        wanted = parse_listing(download(source, LISTING_LIMIT), count)
        if not wanted:
            raise ValueError("NOAA no publicó cuadros históricos compatibles")
    except Exception as exc:
        if cached is None:
            raise
        result = dict(cached)
        result["warning"] = "No se actualizó el historial; se usan cuadros guardados."
        LOG.warning("No se pudo consultar el historial NOAA: %s", exc)
        return result
    fetched_at = time.time()
    failures = 0
    cancelled = False
    # Newest first: if cancellation or a connection issue interrupts a first
    # load, a useful recent image can still be shown. Returned order is oldest
    # first for chronological playback.
    for record in reversed(wanted):
        if stop is not None and stop.is_set():
            cancelled = True
            break
        if record["key"] in available:
            continue
        try:
            image = download(record["url"], IMAGE_LIMIT)
            if not _image_valid(image):
                raise ValueError("NOAA no devolvió un JPEG completo")
            available[record["key"]] = dict(record, image=image)
        except Exception as exc:
            failures += 1
            LOG.warning("No se pudo descargar el cuadro %s: %s", record["key"], exc)
    if not available:
        if cancelled:
            raise InterruptedError("Descarga satelital cancelada")
        raise ValueError("No se pudo descargar ningún cuadro satelital válido")
    frames = sorted(available.values(), key=lambda item: item["captured_at"])[-count:]
    event = {"kind": "satellite_history", "frames": frames, "fetched_at": fetched_at, "latest_requested": wanted[-1]["key"]}
    if failures or cancelled:
        event["warning"] = "Historial incompleto; se conservan los cuadros disponibles."
    try:
        _save_history(config, directory, source, event)
    except (OSError, ValueError) as exc:
        LOG.warning("No se pudo guardar el historial satelital: %s", exc)
        if not event.get("warning"):
            event["warning"] = "Se descargó el historial, pero no pudo guardarse en caché."
    return event
