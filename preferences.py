"""Local display preferences, independent from location and weather settings."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from data import atomic_write

MODES = ("dark", "light")

def load_theme(directory: Path, fallback: str = "dark") -> str:
    default = fallback if fallback in MODES else "dark"
    try:
        path = directory / "preferences.json"
        if path.stat().st_size > 4096:
            return default
        entry = json.loads(path.read_text(encoding="utf-8"))
        mode = entry.get("theme") if isinstance(entry, dict) else None
        return mode if mode in MODES else default
    except (OSError, ValueError):
        return default

def save_theme(directory: Path, mode: str) -> bool:
    if mode not in MODES:
        raise ValueError("Modo de pantalla inválido")
    try:
        atomic_write(directory / "preferences.json", json.dumps({"theme": mode}).encode("utf-8"))
        return True
    except OSError as exc:
        logging.getLogger(__name__).warning("No se pudo guardar el modo de pantalla: %s", exc)
        return False
