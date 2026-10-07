"""Visor satelital con encuadre y animación; el controlador conserva el pie."""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pygame

from theme import apply_theme, panel
from geography import MapOverlay, project
from geo_satellite import BBOX, frame_time, valid_extent


class SatelliteView:
    """Recibe imágenes ya descargadas y dibuja únicamente sobre los primeros 278 px."""

    BG = (240, 245, 249)
    INK = (22, 54, 76)
    ACCENT = (14, 111, 130)
    WHITE = (255, 255, 255)
    MUTED = (73, 94, 110)
    WARNING = (255, 211, 146)
    VERACRUZ_CENTER = (0.61, 0.55)
    VERACRUZ_ZOOM = 2.5
    VERACRUZ_GEOGRAPHIC_ZOOM = 3.2
    MAX_ZOOM = 10.0
    DETAIL_ZOOM = 4.0

    def __init__(self, surface, timezone="America/Mexico_City", theme="dark"):
        self.surface = surface
        self.timezone = timezone
        self.set_theme(theme)
        self.rect = pygame.Rect(6, 6, 370, 266)
        self.sidebar = pygame.Rect(382, 6, 92, 266)
        self.playing = True
        self.zoom = 1.0
        self.center = (0.5, 0.5)
        self.frame_index = 0
        self.frames = []
        self.fetched_at = None
        self.warning = None
        self.buttons = {
            "zoom_out": pygame.Rect(382, 10, 44, 36),
            "zoom_in": pygame.Rect(430, 10, 44, 36),
            "mexico": pygame.Rect(382, 66, 92, 34),
            "veracruz": pygame.Rect(382, 104, 92, 34),
            "play": pygame.Rect(382, 142, 92, 34),
        }
        if not pygame.font.get_init():
            pygame.font.init()
        regular = pygame.font.match_font("dejavusans")
        bold = pygame.font.match_font("dejavusans", bold=True) or regular
        self.fonts = {size: pygame.font.Font(regular, size) for size in (13, 14, 16, 18, 19, 24)}
        self.bold = {size: pygame.font.Font(bold, size) for size in (13, 14, 19, 24)}
        self._render_cache = OrderedDict()
        self._last_tick = None
        self._drag = None
        self._last_pointer = None
        self._preset = "mexico"
        self.map_overlay = MapOverlay()
        self.detail = None
        self.detail_status = "idle"
        self._detail_signature = None
        self._detail_token = 0
        self._detail_due = None
        self._detail_sent = False
        self._detail_canvas = None
        self._detail_retry_after = None
        self._detail_failures = 0

    def set_theme(self, mode):
        # La paleta no cambia el encuadre, la reproducción ni la caché de recortes.
        apply_theme(self, mode)

    @staticmethod
    def _stamp(value):
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            return None
        return float(value) if math.isfinite(value) and value >= 0 else None

    def _current(self):
        if isinstance(self.frame_index, int) and 0 <= self.frame_index < len(self.frames):
            return self.frames[self.frame_index]
        return None

    def set_frames(self, frames, fetched_at, warning=None):
        previous = self._current()
        previous_key = previous["key"] if previous else None
        valid = {}
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            key, image = frame.get("key"), frame.get("image")
            if not isinstance(key, str) or not key or not isinstance(image, pygame.Surface):
                continue
            if min(image.get_size()) <= 0:
                continue
            valid[key] = {**frame, "key": key, "image": image,
                          "captured_at": self._stamp(frame.get("captured_at"))}
        if not valid:
            self.warning = warning or "No se recibieron imágenes válidas"
            return
        self.frames = sorted(valid.values(), key=lambda row: row["captured_at"] or 0)
        keys = [row["key"] for row in self.frames]
        self.frame_index = keys.index(previous_key) if previous_key in keys else (0 if self.playing else len(keys) - 1)
        self.fetched_at = self._stamp(fetched_at)
        self.warning = warning
        self._last_tick = None
        self._render_cache.clear()
        current = self._current()
        if self._preset == "veracruz" and current and current.get("extent") != (previous or {}).get("extent"):
            self.center = self._veracruz_center()
            if current.get("crs") == "EPSG:4326":
                self.zoom = self.VERACRUZ_GEOGRAPHIC_ZOOM
        self._clamp_center()

    def _veracruz_center(self):
        frame = self._current()
        if frame and frame.get("crs") == "EPSG:4326" and valid_extent(frame.get("extent")):
            size = frame["image"].get_size()
            point = project(-96.91589, 19.53124, frame["extent"], size)
            return point[0] / size[0], point[1] / size[1]
        return self.VERACRUZ_CENTER

    def tick(self, monotonic_now):
        moment = self._stamp(monotonic_now)
        if moment is None or self._current() is None:
            return False
        if self._last_tick is None or moment < self._last_tick or not self.playing or len(self.frames) < 2:
            self._last_tick = moment
            return False
        steps = int(moment - self._last_tick)
        if steps < 1:
            return False
        self._last_tick += steps
        old_index = self.frame_index
        self.frame_index = (self.frame_index + steps) % len(self.frames)
        self._clamp_center()
        return self.frame_index != old_index

    def _scale(self, image, zoom=None):
        width, height = image.get_size()
        return min(self.rect.width / width, self.rect.height / height) * (self.zoom if zoom is None else zoom)

    def _clamp_center(self):
        frame = self._current()
        if frame is None:
            return
        image = frame["image"]
        scale = self._scale(image)
        result = []
        for center, image_size, viewport_size in zip(self.center, image.get_size(), self.rect.size):
            half = viewport_size / (2 * image_size * scale)
            result.append(0.5 if half >= 0.5 else min(1 - half, max(half, center)))
        self.center = tuple(result)

    def _set_zoom(self, value, anchor=None):
        value = max(1.0, min(self.MAX_ZOOM, float(value)))
        if self.zoom <= self.DETAIL_ZOOM < value:
            self.playing = False
            self._last_tick = None
        frame = self._current()
        if frame is not None and anchor is not None:
            image = frame["image"]
            old_scale, new_scale = self._scale(image), self._scale(image, value)
            self.center = tuple(
                center + (point - middle) / size * (1 / old_scale - 1 / new_scale)
                for center, point, middle, size in zip(self.center, anchor, self.rect.center, image.get_size())
            )
        self.zoom = value
        self._preset = None
        self._clamp_center()

    def _pan(self, dx, dy):
        frame = self._current()
        if frame is None:
            return
        image, center = frame["image"], self.center
        scale = self._scale(image)
        self.center = (center[0] - dx / (image.get_width() * scale),
                       center[1] - dy / (image.get_height() * scale))
        self._preset = None
        self._clamp_center()

    def _action(self, name):
        if name == "zoom_in":
            self._set_zoom(self.zoom * 1.25)
        elif name == "zoom_out":
            self._set_zoom(self.zoom / 1.25)
        elif name == "mexico":
            self.zoom, self.center, self._preset = 1.0, (0.5, 0.5), "mexico"
        elif name == "veracruz":
            self.zoom, self.center, self._preset = self.VERACRUZ_ZOOM, self._veracruz_center(), "veracruz"
            frame = self._current()
            if frame and frame.get("crs") == "EPSG:4326" and valid_extent(frame.get("extent")):
                self.zoom = self.VERACRUZ_GEOGRAPHIC_ZOOM
            self._clamp_center()
        elif name == "play":
            self.playing = not self.playing
            self._last_tick = None

    def handle_event(self, event):
        """Consume los controles internos; deja libres Escape y los botones del pie."""
        mouse_types = (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL)
        if event.type in mouse_types and getattr(event, "touch", False):
            return False
        if event.type == pygame.KEYDOWN:
            actions = {
                pygame.K_PLUS: "zoom_in", pygame.K_EQUALS: "zoom_in", pygame.K_KP_PLUS: "zoom_in",
                pygame.K_MINUS: "zoom_out", pygame.K_KP_MINUS: "zoom_out",
                pygame.K_HOME: "mexico", pygame.K_m: "mexico", pygame.K_v: "veracruz",
                pygame.K_p: "play", pygame.K_SPACE: "play",
            }
            if event.key in actions:
                self._action(actions[event.key])
                return True
            pans = {pygame.K_LEFT: (self.rect.width * .12, 0),
                    pygame.K_RIGHT: (-self.rect.width * .12, 0),
                    pygame.K_UP: (0, self.rect.height * .12),
                    pygame.K_DOWN: (0, -self.rect.height * .12)}
            if event.key in pans:
                self._pan(*pans[event.key])
                return True
            return False
        if event.type == pygame.MOUSEWHEEL:
            point = getattr(event, "pos", None) or self._last_pointer or pygame.mouse.get_pos()
            if self.rect.collidepoint(point):
                delta = event.y * (-1 if getattr(event, "flipped", False) else 1)
                self._set_zoom(self.zoom * 1.15 ** max(-8, min(8, delta)), point)
                return True
            return False
        finger_types = (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP)
        if event.type not in mouse_types + finger_types:
            return False
        finger = event.type in finger_types
        point = (round(event.x * 480), round(event.y * 320)) if finger else event.pos
        identity = ("finger", getattr(event, "finger_id", 0)) if finger else ("mouse", 0)
        self._last_pointer = point
        down = event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN)
        up = event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP)
        motion = event.type in (pygame.MOUSEMOTION, pygame.FINGERMOTION)
        if down:
            if not finger and event.button in (4, 5) and self.rect.collidepoint(point):
                self._set_zoom(self.zoom * (1.15 if event.button == 4 else 1 / 1.15), point)
                return True
            if not finger and event.button != 1:
                return False
            for name, rect in self.buttons.items():
                if rect.collidepoint(point):
                    self._action(name)
                    return True
            if self.rect.collidepoint(point):
                if self._drag is None:
                    self._drag = (identity, point)
                return True
        elif self._drag is not None and self._drag[0] == identity:
            if motion:
                last = self._drag[1]
                self._pan(point[0] - last[0], point[1] - last[1])
                self._drag = (identity, point)
                return True
            if up:
                self._drag = None
                return True
        return self.rect.collidepoint(point) or self.sidebar.collidepoint(point)

    def _render_image(self, frame):
        image = frame["image"]
        key = (frame["key"], id(image), image.get_size(), round(self.zoom, 6),
               tuple(round(value, 7) for value in self.center))
        if key in self._render_cache:
            self._render_cache.move_to_end(key)
            return self._render_cache[key]
        canvas = pygame.Surface(self.rect.size)
        canvas.fill(self.CANVAS)
        scale = self._scale(image)
        cx, cy = self.center[0] * image.get_width(), self.center[1] * image.get_height()
        left = max(0, math.floor(cx - self.rect.width / (2 * scale)))
        top = max(0, math.floor(cy - self.rect.height / (2 * scale)))
        right = min(image.get_width(), math.ceil(cx + self.rect.width / (2 * scale)))
        bottom = min(image.get_height(), math.ceil(cy + self.rect.height / (2 * scale)))
        crop = image.subsurface(pygame.Rect(left, top, right - left, bottom - top))
        size = (max(1, round(crop.get_width() * scale)), max(1, round(crop.get_height() * scale)))
        offset = (round(self.rect.width / 2 + (left - cx) * scale),
                  round(self.rect.height / 2 + (top - cy) * scale))
        canvas.blit(pygame.transform.smoothscale(crop, size), offset)
        self._render_cache[key] = canvas
        while len(self._render_cache) > 8:
            self._render_cache.popitem(last=False)
        return canvas

    def _visible_extent(self):
        frame = self._current()
        if not frame or frame.get("crs") != "EPSG:4326" or not valid_extent(frame.get("extent")):
            return None
        self._clamp_center()
        xmin, ymin, xmax, ymax = frame["extent"]
        image = frame["image"]
        scale = self._scale(image)
        half_x = (xmax - xmin) * self.rect.width / (2 * image.get_width() * scale)
        half_y = (ymax - ymin) * self.rect.height / (2 * image.get_height() * scale)
        lon = xmin + self.center[0] * (xmax - xmin)
        lat = ymax - self.center[1] * (ymax - ymin)
        return [round(value, 6) for value in (max(xmin, lon - half_x), max(ymin, lat - half_y),
                                            min(xmax, lon + half_x), min(ymax, lat + half_y))]

    def _detail_target(self):
        frame = self._current()
        if self.playing or self.zoom <= self.DETAIL_ZOOM or not frame or frame.get("source") != "NOAA":
            return None
        bounds = self._visible_extent()
        if not bounds or bounds[0] < BBOX[0] or bounds[1] < BBOX[1] or bounds[2] > BBOX[2] or bounds[3] > BBOX[3]:
            return None
        try:
            if frame_time(frame["key"]) != frame["captured_at"]:
                return None
        except (ValueError, TypeError):
            return None
        return (frame["key"], frame["captured_at"], tuple(bounds))

    def _has_detail(self, target):
        if not target or not self.detail or self.playing:
            return False
        key, captured, bounds = target
        detail = self.detail
        if key != detail["key"] or captured != detail["captured_at"]:
            return False
        area = detail["extent"]
        epsilon = 0.000002
        return (bounds[0] >= area[0] - epsilon and bounds[1] >= area[1] - epsilon
                and bounds[2] <= area[2] + epsilon and bounds[3] <= area[3] + epsilon)

    def poll_detail(self, monotonic_now, enabled=True):
        """Wait for a stable viewport, then submit one bounded regional request."""
        if not enabled:
            self._drag = None
        target = self._detail_target() if enabled else None
        if target != self._detail_signature:
            self._detail_token += 1
            self._detail_signature = target
            self._detail_due = monotonic_now + 1.2 if target else None
            self._detail_sent = False
            self.detail_status = "preparing" if target else "idle"
            self._detail_retry_after = None
            self._detail_failures = 0
        if target and self._has_detail(target):
            self.detail_status = "ready"
            return None
        if target and self.detail_status == "failed" and monotonic_now >= self._detail_retry_after:
            self._detail_token += 1
            self._detail_sent = False
            self._detail_due = monotonic_now
        if not target or self._detail_sent or monotonic_now < self._detail_due or self._drag:
            return None
        self._detail_sent = True
        self.detail_status = "loading"
        return {"request_token": self._detail_token, "key": target[0],
                "captured_at": target[1], "extent": list(target[2])}

    def expects_detail(self, token):
        return (self._detail_sent and token == self._detail_token and self._detail_signature is not None
                and self._detail_target() == self._detail_signature)

    def detail_failed(self, monotonic_now=None):
        self.detail_status = "failed"
        self._detail_failures += 1
        self._detail_retry_after = (time.monotonic() if monotonic_now is None else monotonic_now) + min(300, 60 * 2 ** min(self._detail_failures - 1, 3))

    def set_detail(self, frame):
        if not isinstance(frame, dict) or not isinstance(frame.get("image"), pygame.Surface):
            raise ValueError("Imagen de detalle inválida")
        image = frame["image"]
        if (min(image.get_size()) < 32 or max(image.get_size()) > 800
                or frame.get("crs") != "EPSG:4326" or not valid_extent(frame.get("extent"))
                or (frame.get("key"), frame.get("captured_at"), tuple(frame["extent"])) != self._detail_signature):
            raise ValueError("El detalle no corresponde al encuadre solicitado")
        self.detail = frame
        self.detail_status = "ready"
        self._detail_canvas = None
        self._detail_retry_after = None
        self._detail_failures = 0

    def _render_detail(self):
        target = self._detail_target()
        if not self._has_detail(target):
            return None
        image, area = self.detail["image"], self.detail["extent"]
        bounds = target[2]
        cache_key = (id(image), bounds)
        if self._detail_canvas and self._detail_canvas[0] == cache_key:
            return self._detail_canvas[1]
        width, height = image.get_size()
        span_x, span_y = area[2] - area[0], area[3] - area[1]
        left = max(0, math.floor((bounds[0] - area[0]) / span_x * width))
        right = min(width, math.ceil((bounds[2] - area[0]) / span_x * width))
        top = max(0, math.floor((area[3] - bounds[3]) / span_y * height))
        bottom = min(height, math.ceil((area[3] - bounds[1]) / span_y * height))
        scale_x = span_x / width * self.rect.width / (bounds[2] - bounds[0])
        scale_y = span_y / height * self.rect.height / (bounds[3] - bounds[1])
        crop = image.subsurface(pygame.Rect(left, top, right - left, bottom - top))
        size = (max(1, round(crop.get_width() * scale_x)), max(1, round(crop.get_height() * scale_y)))
        offset = (round((area[0] + left / width * span_x - bounds[0]) / (bounds[2] - bounds[0]) * self.rect.width),
                  round((bounds[3] - area[3] + top / height * span_y) / (bounds[3] - bounds[1]) * self.rect.height))
        canvas = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        canvas.blit(pygame.transform.smoothscale(crop, size), offset)
        self._detail_canvas = (cache_key, canvas)
        return canvas

    def _text(self, value, x, y, size=13, color=None, bold=False, width=None):
        font = (self.bold if bold else self.fonts)[size]
        text = str(value)
        if width is not None:
            while text and font.size(text)[0] > width:
                text = text[:-2] + "…" if len(text) > 1 else ""
        self.surface.blit(font.render(text, True, color or self.INK), (x, y))

    def _center_text(self, value, y, size=13, color=None, bold=False):
        font = (self.bold if bold else self.fonts)[size]
        self._text(value, self.sidebar.centerx - font.size(str(value))[0] // 2,
                   y, size, color, bold, self.sidebar.width - 4)

    def _age(self, stamp, now):
        if stamp is None:
            return None, "hora no disponible"
        seconds = now.timestamp() - stamp
        if seconds < -300:
            return None, "hora no verificada"
        seconds = max(0, seconds)
        if seconds < 60:
            label = "hace segundos"
        elif seconds < 3600:
            label = f"hace {int(seconds // 60)} min"
        elif seconds < 86400:
            label = f"hace {int(seconds // 3600)} h"
        else:
            days = int(seconds // 86400)
            label = f"hace {days} " + ("día" if days == 1 else "días")
        return seconds, label

    def draw(self, now, error=None):
        old_clip = self.surface.get_clip()
        self.surface.set_clip(pygame.Rect(0, 0, 480, 278))
        try:
            frame = self._current()
            mapped = False
            panel(self.surface, self.sidebar, self.palette)
            pygame.draw.rect(self.surface, self.CANVAS, self.rect)
            if frame is not None:
                self._clamp_center()
                self.surface.blit(self._render_image(frame), self.rect)
                detail_canvas = self._render_detail()
                if detail_canvas is not None:
                    self.surface.blit(detail_canvas, self.rect)
                mapped = self.map_overlay.draw(self.surface, self.rect, frame, self.zoom, self.center, self.palette)
            else:
                self._text("Sin imágenes disponibles", 30, 98, 18, self.IMAGE_INK, width=322)
                self._text("Esperando imágenes válidas…", 30, 132, 13, self.IMAGE_INK, width=322)
            source = "CIRA/NOAA" if frame and (frame.get("source") == "NOAA" or
                     frame["key"] != "static" and frame["captured_at"] is not None) else "Satélite"
            credit = pygame.Surface((150, 23), pygame.SRCALPHA)
            credit.fill(self.OVERLAY)
            self.surface.blit(credit, (10, 10))
            self._text(source + (" · GOES" if source == "CIRA/NOAA" else ""), 15, 13, 13, self.IMAGE_INK, width=142)
            for name, rect in self.buttons.items():
                selected = name == "play" and self.playing or name == self._preset
                panel(self.surface, rect, self.palette, active=selected)
                label = {"zoom_out": "−", "zoom_in": "+", "mexico": "México",
                         "veracruz": "Veracruz", "play": "Pausa" if self.playing else "Reproducir"}[name]
                size = 24 if name.startswith("zoom_") else 14
                font = self.bold[size]
                x, y = rect.centerx - font.size(label)[0] // 2, rect.centery - font.get_height() // 2
                self._text(label, x, y, size, self.ACCENT_INK if selected else self.ACCENT,
                           bold=True, width=rect.width - 4)
            self._center_text(f"{self.zoom:.1f}×", 48, color=self.ACCENT)
            self._center_text(f"{self.frame_index + 1}/{len(self.frames)}" if frame else "0/0", 180)
            self._center_text("Captura", 198)
            if frame and frame["captured_at"] is not None:
                try:
                    captured = datetime.fromtimestamp(frame["captured_at"], ZoneInfo(self.timezone))
                    self._center_text(captured.strftime("%H:%M"), 214, 19, self.ACCENT, bold=True)
                    self._center_text(captured.strftime("%d/%m/%y"), 239)
                except (ValueError, OverflowError, OSError, ZoneInfoNotFoundError):
                    self._center_text("Hora no", 214)
                    self._center_text("disponible", 230)
            else:
                self._center_text("Hora no", 214)
                self._center_text("disponible", 230)
            self._center_text("NOAA" if source == "CIRA/NOAA" else "Satélite", 255)
            capture_age, capture_label = self._age(frame["captured_at"] if frame else None, now)
            check_age, check_label = self._age(self.fetched_at, now)
            stamps = [row["captured_at"] for row in self.frames if row["captured_at"] is not None]
            latest_age, latest_label = self._age(max(stamps) if stamps else None, now)
            line1 = "Captura " + capture_label + " · consulta " + check_label
            line2 = "Estados y ciudades · Natural Earth / GeoNames" if mapped else "Fuente sin coordenadas · sin etiquetas"
            caution = False
            if error:
                line2 = line1
                line1 = "Consulta fallida · imágenes guardadas" if frame else "No se pudo consultar"
                caution = True
            elif self.warning:
                line2, line1, caution = line1, self.warning, True
            elif latest_age is not None and latest_age >= 1800:
                line2, line1, caution = line1, "Última captura antigua: " + latest_label, True
            elif check_age is not None and check_age >= 1200:
                line2, line1, caution = line1, "Imágenes guardadas · consulta antigua", True
            if frame and self.zoom > self.DETAIL_ZOOM:
                if self.playing:
                    line2 = "Pausa para cargar más detalle"
                elif self._detail_target() is None:
                    line2 = "Ampliación · fuente sin detalle regional"
                else:
                    line2 = {"idle": "Ampliación · preparando detalle",
                             "preparing": "Preparando detalle de esta zona…",
                             "loading": "Descargando detalle de esta zona…",
                             "ready": "Detalle regional · estados y ciudades",
                             "failed": "Detalle no disponible · vista conservada"}[self.detail_status]
            band = pygame.Surface((self.rect.width, 38), pygame.SRCALPHA)
            band.fill(self.OVERLAY)
            self.surface.blit(band, (self.rect.left, 234))
            color = self.IMAGE_WARNING if caution else self.IMAGE_INK
            self._text(line1, 13, 236, 13, color, width=354)
            self._text(line2, 13, 253, 13, color, width=354)
            pygame.draw.rect(self.surface, self.ACCENT, self.rect, width=1)
        finally:
            self.surface.set_clip(old_clip)
