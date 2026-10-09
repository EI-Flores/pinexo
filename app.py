#!/usr/bin/env python3
"""PiNexo: lightweight weather and satellite views in the labwc session."""
from __future__ import annotations

import argparse
import io
import json
import logging
import math
import os
import queue
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from data import fetch_weather, read_cache, run_downloads, save_satellite
from satellite_data import frame_count, read_history
from preferences import load_theme, save_theme
from geo_satellite import read_history as read_geographic_history

BASE = Path(__file__).resolve().parent
LOG = logging.getLogger("pi-clima")


def graphical_environment() -> None:
    """Reuse a single compositor belonging to this user; never guess its socket."""
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
        return
    if not Path("/proc").is_dir() or not hasattr(os, "getuid"):
        return
    candidates = []
    for process in Path("/proc").iterdir():
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            if (process / "comm").read_text().strip() != "labwc":
                continue
            environment = dict(part.split("=", 1) for part in (process / "environ").read_bytes().decode("utf-8", "replace").split("\0") if "=" in part)
            runtime = environment.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            # labwc sets WAYLAND_DISPLAY for its children, not necessarily itself.
            socket = environment.get("WAYLAND_DISPLAY")
            if not socket:
                sockets = [str(p.name) for p in Path(runtime).glob("wayland-*") if p.is_socket()]
                if len(sockets) == 1:
                    socket = sockets[0]
            if socket and (Path(socket) if socket.startswith("/") else Path(runtime) / socket).is_socket():
                environment.update(WAYLAND_DISPLAY=socket, XDG_RUNTIME_DIR=runtime)
                candidates.append(environment)
        except (OSError, ValueError):
            continue
    if len(candidates) != 1:
        raise RuntimeError("No se encontró una sesión gráfica única. Abre una terminal del escritorio visible en el LCD y ejecuta ahí la aplicación.")
    for key in ("WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DISPLAY", "XDG_SESSION_TYPE"):
        if candidates[0].get(key):
            os.environ[key] = candidates[0][key]


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not -90 <= float(config["latitude"]) <= 90 or not -180 <= float(config["longitude"]) <= 180:
        raise ValueError("Coordenadas inválidas")
    ZoneInfo(config["timezone"])
    for key in ("weather_refresh_seconds", "satellite_refresh_seconds", "page_seconds"):
        if float(config[key]) < (30 if key != "page_seconds" else 10):
            raise ValueError(f"Intervalo demasiado corto: {key}")
    if not config["satellite_url"].startswith("https://"):
        raise ValueError("La imagen satelital requiere HTTPS")
    threshold = config.get("rain_alert_probability", 60)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError("El umbral de probabilidad de lluvia debe estar entre 0 y 100")
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Panel de clima 480×320 para la Raspberry Pi")
    parser.add_argument("--config", type=Path, default=BASE / "config.json")
    parser.add_argument("--windowed", action="store_true", help="Vista previa en una ventana")
    parser.add_argument("--display", type=int, help="Índice de pantalla SDL, únicamente si hay varias")
    parser.add_argument("--check-weather", action="store_true", help="Verificar la descarga sin abrir una ventana")
    parser.add_argument("--demo", action="store_true", help="Datos ilustrativos locales; no usa Internet")
    parser.add_argument("--service", action="store_true", help="Usar la sesión labwc del usuario para el servicio automático")
    parser.add_argument("--smoke-seconds", type=float, help=argparse.SUPPRESS)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = load_config(args.config)
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "pi-clima"
    if args.check_weather:
        event = fetch_weather(config, cache)
        current = event["forecast"]["current"]
        print(f"{config['city']}: {current.get('temperature_2m')} °C; datos válidos {current['time']} ({config['timezone']}).")
        return 0
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    if args.service:
        # A user manager may hold a stale or forwarded graphical environment.
        # Discover the current session rather than reusing those display names.
        for name in ("WAYLAND_DISPLAY", "DISPLAY", "SDL_VIDEODRIVER"):
            os.environ.pop(name, None)
    if os.environ.get("SDL_VIDEODRIVER") != "dummy":
        graphical_environment()
        if os.environ.get("WAYLAND_DISPLAY"):
            os.environ.setdefault("SDL_VIDEODRIVER", "wayland")
    try:
        import pygame
        from forecast_ui import ForecastDashboard as Dashboard
        from satellite_ui import SatelliteView
        from home_ui import HomeView
        from detail_worker import DetailWorker
    except ImportError as exc:
        raise RuntimeError("Instala el paquete: sudo apt install python3-pygame") from exc
    try:
        pygame.display.init()
        pygame.font.init()
        desktops = pygame.display.get_desktop_sizes()
        if args.windowed:
            index = args.display if args.display is not None else 0
            flags = 0
        else:
            suitable = [i for i, size in enumerate(desktops) if tuple(size) == (480, 320)]
            if args.display is not None:
                index = args.display
            elif len(suitable) == 1:
                index = suitable[0]
            else:
                raise RuntimeError(f"No se encontró un LCD único de 480×320. Pantallas detectadas: {desktops}. Usa --windowed para previsualizar y comparte esta salida.")
            flags = pygame.FULLSCREEN
        if index < 0 or index >= len(desktops):
            raise RuntimeError(f"Índice de pantalla inválido: {index}")
        surface = pygame.display.set_mode((480, 320), flags, display=index)
        if surface.get_size() != (480, 320):
            raise RuntimeError(f"La sesión dio un tamaño diferente: {surface.get_size()}. Prueba --windowed.")
        pygame.display.set_caption("PiNexo · Panel personal")
        pygame.mouse.set_visible(True)
        theme = load_theme(cache, config.get("theme", "dark"))
        dashboard = Dashboard(surface, config["city"], config["timezone"], config.get("rain_alert_probability", 60), theme=theme)
        satellite_view = SatelliteView(surface, config["timezone"], theme=theme)
        home_view = HomeView(surface, timezone=config["timezone"], theme=theme)
        events = queue.Queue()
        stop = threading.Event()
        detail_worker = None
        state = {"weather": None, "satellite": None}
        stamps = {"weather": None, "satellite": None}
        errors = {"weather": None, "satellite": None}
        if args.demo:
            demo = json.loads((BASE / "demo.json").read_text(encoding="utf-8"))
            anchor = datetime.now(ZoneInfo(config["timezone"])).replace(minute=0, second=0, microsecond=0)
            demo["current"]["time"] = anchor.isoformat(timespec="minutes")[:16]
            demo["hourly"]["time"] = [(anchor + timedelta(hours=i)).isoformat(timespec="minutes")[:16] for i in range(12)]
            demo["daily"] = {
                "time": [(anchor + timedelta(days=i)).date().isoformat() for i in range(4)],
                "temperature_2m_min": [17, 18, 17, 16],
                "temperature_2m_max": [24, 25, 23, 22],
                "weather_code": [53, 3, 61, 2],
                "precipitation_probability_max": [70, 30, 80, 20],
                "sunrise": [(anchor + timedelta(days=i)).replace(hour=6, minute=20).isoformat(timespec="minutes")[:16] for i in range(4)],
                "sunset": [(anchor + timedelta(days=i)).replace(hour=18, minute=15).isoformat(timespec="minutes")[:16] for i in range(4)],
            }
            state["weather"] = demo
            stamps["weather"] = time.time()
            dashboard.title = "Xalapa · DEMOSTRACIÓN"
        else:
            for event in read_cache(config, cache):
                events.put(event)
            history = read_geographic_history(config, cache) or read_history(config, cache)
            if history:
                events.put(history)
            threading.Thread(target=run_downloads, args=(config, cache, events, stop), daemon=True).start()
            detail_worker = DetailWorker(cache, events, stop)
            detail_worker.start()
        page = "home"
        rotation = ["weather", "today", "days", "satellite"]
        switched = time.monotonic()
        started = switched
        minute = None
        dirty = True
        running = True
        exit_code = 0
        while running:
            now = datetime.now(ZoneInfo(config["timezone"]))
            while not events.empty():
                event = events.get_nowait()
                kind = event["kind"]
                if kind == "satellite_detail":
                    if satellite_view.expects_detail(event.get("request_token")):
                        try:
                            if event.get("error"):
                                satellite_view.detail_failed()
                            else:
                                frame = event["frames"][0]
                                image = pygame.image.load(io.BytesIO(frame["image"]), "detail.jpg")
                                satellite_view.set_detail(dict(frame, image=image.convert()))
                            dirty = True
                        except (pygame.error, ValueError, KeyError, IndexError) as exc:
                            LOG.warning("No se pudo abrir el detalle: %s", exc)
                            satellite_view.detail_failed()
                            dirty = True
                    continue
                state_kind = "satellite" if kind == "satellite_history" else kind
                if "error" in event:
                    errors[state_kind] = event["error"]
                elif kind == "weather":
                    state[kind], stamps[kind], errors[kind] = event["forecast"], event["fetched_at"], None
                elif kind == "satellite":
                    try:
                        image = pygame.image.load(io.BytesIO(event["image"]), "satellite.jpg").convert()
                        state[kind], stamps[kind], errors[kind] = image, event["fetched_at"], None
                        satellite_view.set_frames([{"key": "static", "captured_at": None, "image": image}], event["fetched_at"])
                        if not args.demo:
                            save_satellite(config, cache, event)
                    except pygame.error as exc:
                        LOG.warning("No se pudo abrir la imagen: %s", exc)
                        errors[kind] = "Imagen inválida"
                elif kind == "satellite_history":
                    frames = []
                    invalid = False
                    for frame in event["frames"][-frame_count(config):]:
                        try:
                            image = pygame.image.load(io.BytesIO(frame["image"]), "satellite.jpg")
                            if image.get_size() != (1000, 1000):
                                raise ValueError("El cuadro no tiene la resolución prevista")
                            frames.append(dict(frame, image=image.convert()))
                        except (pygame.error, ValueError) as exc:
                            invalid = True
                            LOG.warning("Se descartó un cuadro satelital: %s", exc)
                    warning = "Se omitieron imágenes inválidas" if invalid else event.get("warning")
                    errors["satellite"] = None
                    if frames:
                        satellite_view.set_frames(frames, event["fetched_at"], warning)
                        stamps["satellite"] = event["fetched_at"]
                    else:
                        errors["satellite"] = "No se pudieron abrir los cuadros satelitales"
                dirty = True
            for event in pygame.event.get():
                target = None
                if event.type == pygame.QUIT:
                    # A compositor closing should not permanently stop the appliance.
                    exit_code = 1 if args.service else 0
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if page == "home":
                        running = False
                    else:
                        target = "home"
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_h:
                    target = "home"
                elif page in ("home", "notifications"):
                    home_view.mode = page
                    target = home_view.handle_event(event)
                    if event.type == pygame.WINDOWEXPOSED:
                        dirty = True
                elif page == "satellite" and satellite_view.handle_event(event):
                    # Interaction holds this view; Tab and footer navigation still work.
                    switched, dirty = time.monotonic(), True
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_d:
                        target = "theme"
                    elif event.key in (pygame.K_SPACE, pygame.K_TAB, pygame.K_RIGHT, pygame.K_LEFT):
                        if page == "sources":
                            target = "weather"
                        else:
                            step = -1 if event.key == pygame.K_LEFT else 1
                            target = rotation[(rotation.index(page) + step) % len(rotation)]
                    elif event.key == pygame.K_1:
                        target = "weather"
                    elif event.key == pygame.K_2:
                        target = "today"
                    elif event.key == pygame.K_3:
                        target = "days"
                    elif event.key == pygame.K_4:
                        target = "satellite"
                    elif event.key == pygame.K_5:
                        target = "sources"
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not getattr(event, "touch", False):
                    target = next((name for name, rect in dashboard.buttons.items() if rect.collidepoint(event.pos)), None)
                elif event.type == pygame.FINGERDOWN:
                    point = (int(event.x * 480), int(event.y * 320))
                    target = next((name for name, rect in dashboard.buttons.items() if rect.collidepoint(point)), None)
                elif event.type == pygame.WINDOWEXPOSED:
                    dirty = True
                if target:
                    if target == "theme":
                        theme = "light" if theme == "dark" else "dark"
                        dashboard.set_theme(theme)
                        satellite_view.set_theme(theme)
                        home_view.set_theme(theme)
                        if not args.demo:
                            save_theme(cache, theme)
                        switched, dirty = time.monotonic(), True
                    elif target == "quit":
                        running = False
                    else:
                        page, switched, dirty = target, time.monotonic(), True
            rotating = page in rotation and (page != "satellite" or satellite_view.playing)
            if rotating and time.monotonic() - switched >= float(config["page_seconds"]):
                page = rotation[(rotation.index(page) + 1) % len(rotation)]
                switched, dirty = time.monotonic(), True
            if minute != now.strftime("%Y%m%d%H%M"):
                minute, dirty = now.strftime("%Y%m%d%H%M"), True
            if page == "satellite" and satellite_view.tick(time.monotonic()):
                dirty = True
            detail_status = satellite_view.detail_status
            request = satellite_view.poll_detail(time.monotonic(), enabled=page == "satellite" and detail_worker is not None)
            if request:
                detail_worker.request(request)
            if satellite_view.detail_status != detail_status:
                dirty = True
            if dirty:
                if page == "home":
                    home_view.draw(now)
                elif page == "notifications":
                    home_view.draw_notifications(now)
                elif page == "sources":
                    dashboard.draw_sources(now)
                elif page == "weather":
                    dashboard.draw_weather(state[page], stamps[page], errors[page], now)
                elif page == "today":
                    dashboard.draw_today(state["weather"], stamps["weather"], errors["weather"], now)
                elif page == "days":
                    dashboard.draw_days(state["weather"], stamps["weather"], errors["weather"], now)
                else:
                    dashboard._base(now, "satellite")
                    satellite_view.draw(now, errors["satellite"])
                pygame.display.flip()
                dirty = False
            if args.smoke_seconds and time.monotonic() - started >= args.smoke_seconds:
                running = False
            # Poll input promptly; redraw only when the view is dirty.
            pygame.time.wait(20)
        stop.set()
        return exit_code
    except pygame.error as exc:
        raise RuntimeError(f"No se pudo abrir la pantalla: {exc}. Prueba desde la terminal del escritorio físico o comparte este mensaje.") from exc
    finally:
        if "stop" in locals():
            stop.set()
        pygame.quit()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print(f"PiNexo: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("PiNexo cerrado.")
        raise SystemExit(0)
