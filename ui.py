"""Interfaz de 480 x 320 para el panel de clima; sin red ni acceso a GPIO."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pygame

from theme import apply_theme, footer_rects, panel


WEATHER_LABELS = {
    0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado",
    3: "Nublado", 45: "Niebla", 48: "Niebla con escarcha",
    51: "Llovizna ligera", 53: "Llovizna", 55: "Llovizna intensa",
    56: "Llovizna helada", 57: "Llovizna helada",
    61: "Lluvia ligera", 63: "Lluvia", 65: "Lluvia intensa",
    66: "Lluvia helada", 67: "Lluvia helada",
    71: "Nieve ligera", 73: "Nieve", 75: "Nieve intensa", 77: "Granos de nieve",
    80: "Chubascos ligeros", 81: "Chubascos", 82: "Chubascos fuertes",
    85: "Chubascos de nieve", 86: "Chubascos de nieve",
    95: "Tormenta", 96: "Tormenta con granizo", 99: "Tormenta con granizo",
}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


class Dashboard:
    """Dibuja vistas; el controlador decide cuándo y por qué cambiar de página."""

    BG = (240, 245, 249)
    INK = (22, 54, 76)
    MUTED = (63, 86, 106)
    ACCENT = (14, 111, 130)
    WHITE = (255, 255, 255)
    GRID = (200, 215, 226)
    WARNING = (130, 63, 18)

    LABELS = {"weather": "Clima", "today": "Hoy", "days": "Días",
              "satellite": "Satélite", "sources": "Fuentes", "home": "Inicio"}

    def __init__(self, surface, title, timezone="America/Mexico_City", theme="dark"):
        self.surface = surface
        self.title = str(title)
        self.timezone = timezone
        self.set_theme(theme)
        if not pygame.font.get_init():
            pygame.font.init()
        regular = pygame.font.match_font("dejavusans")
        bold = pygame.font.match_font("dejavusans", bold=True) or regular
        self.fonts = {
            size: pygame.font.Font(regular, size)
            for size in (13, 14, 15, 16, 18, 19, 20, 22, 24)
        }
        self.bold = {
            size: pygame.font.Font(bold, size)
            for size in (14, 16, 19, 20, 22, 24, 34, 66)
        }
        self.buttons = footer_rects(self.LABELS)

    def set_theme(self, mode):
        apply_theme(self, mode)

    def _text(self, text, x, y, size=15, color=None, bold=False, max_width=None):
        font = (self.bold if bold else self.fonts)[size]
        value = str(text)
        if max_width is not None and font.size(value)[0] > max_width:
            while value and font.size(value + "…")[0] > max_width:
                value = value[:-1]
            value += "…"
        rendered = font.render(value, True, color or self.INK)
        self.surface.blit(rendered, (x, y))
        return rendered.get_rect(topleft=(x, y))

    def _center(self, text, y, size=15, color=None, bold=False):
        font = (self.bold if bold else self.fonts)[size]
        return self._text(text, (480 - font.size(str(text))[0]) // 2,
                          y, size, color, bold, 456)

    def _wrap(self, text, width, size=15):
        font = self.fonts[size]
        lines = []
        line = ""
        for word in str(text).split():
            trial = (line + " " + word).strip()
            if line and font.size(trial)[0] > width:
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        return lines

    def _base(self, now, active):
        self.surface.fill(self.BG)
        pygame.draw.rect(self.surface, self.PANEL, (0, 0, 480, 48))
        pygame.draw.line(self.surface, self.ACCENT, (0, 47), (479, 47))
        self._text(self.title, 14, 10, 19, max_width=357)
        self._text(now.strftime("%H:%M"), 397, 11, 19, self.ACCENT, bold=True)
        for name, rect in self.buttons.items():
            selected = name == active
            panel(self.surface, rect, self.palette, active=selected)
            label = ("Claro" if self.theme == "dark" else "Oscuro") if name == "theme" else self.LABELS[name]
            width, height = self.bold[14].size(label)
            self._text(label, rect.centerx - width // 2,
                       rect.centery - height // 2, 14,
                       self.ACCENT_INK if selected else self.INK, bold=True)

    def _download_time(self, fetched_at, now):
        if fetched_at is None:
            return None
        try:
            tz = now.tzinfo or ZoneInfo(self.timezone)
            return datetime.fromtimestamp(float(fetched_at), tz).strftime("%H:%M")
        except (ValueError, OverflowError, OSError, ZoneInfoNotFoundError):
            return None

    def _download_age(self, fetched_at, now):
        if fetched_at is None:
            return None, None
        try:
            seconds = now.timestamp() - float(fetched_at)
            if not math.isfinite(seconds):
                return None, None
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
        except (ValueError, TypeError, OverflowError, OSError):
            return None, None

    def _status(self, has_data, fetched_at, error, now, satellite=False):
        stamp = self._download_time(fetched_at, now)
        age_seconds, age_label = self._download_age(fetched_at, now)
        old = age_seconds is not None and age_seconds >= (1200 if satellite else 1800)
        if error:
            text = "Descarga fallida · datos guardados" if has_data else "No se pudo descargar"
            if has_data and stamp:
                text += " (" + stamp + (" · " + age_label if age_label else "") + ")"
            elif has_data:
                text += " · hora desconocida"
            color = self.WARNING
        elif has_data and stamp:
            text = ("Descargada " if satellite else "Datos descargados ") + stamp
            if old or age_seconds is None:
                text += " · " + (age_label or "edad desconocida")
            color = self.WARNING if old or age_seconds is None else self.MUTED
        elif has_data:
            text = ("Imagen guardada" if satellite else "Datos guardados") + " · hora desconocida"
            color = self.WARNING
        else:
            text = "Consultando el satélite…" if satellite else "Consultando el clima…"
            color = self.MUTED
        self._center(text, 260, 13, color)

    def _weather_icon(self, code, is_day):
        # Icono propio: símbolos grandes que no dependen de un archivo externo.
        cx, cy = 375, 105
        if code in (0, 1, 2):
            if is_day:
                for angle in range(0, 360, 45):
                    theta = math.radians(angle)
                    p1 = (round(cx + 27 * math.cos(theta)), round(cy + 27 * math.sin(theta)))
                    p2 = (round(cx + 36 * math.cos(theta)), round(cy + 36 * math.sin(theta)))
                    pygame.draw.line(self.surface, self.SUN, p1, p2, 2)
                pygame.draw.circle(self.surface, self.SUN, (cx, cy), 20, width=3)
            else:
                pygame.draw.circle(self.surface, self.ACCENT, (cx, cy), 22)
                pygame.draw.circle(self.surface, self.PANEL, (cx + 10, cy - 7), 21)
        if code != 0:
            cloud = self.GRID if code is None else self.CLOUD
            pygame.draw.circle(self.surface, cloud, (cx - 20, cy + 15), 17)
            pygame.draw.circle(self.surface, cloud, (cx, cy + 6), 23)
            pygame.draw.circle(self.surface, cloud, (cx + 23, cy + 17), 16)
            pygame.draw.rect(self.surface, cloud, (cx - 23, cy + 14, 48, 21), border_radius=8)
            pygame.draw.line(self.surface, self.ACCENT, (cx - 26, cy + 34), (cx + 24, cy + 34), 2)
        if code is not None and code >= 51:
            for dx in (-16, 0, 16):
                pygame.draw.line(self.surface, self.ACCENT,
                                 (cx + dx + 3, cy + 44), (cx + dx - 2, cy + 54), 3)

    def _hours(self, forecast, now):
        hourly = forecast.get("hourly") or {}
        times = hourly.get("time") or []
        temperatures = hourly.get("temperature_2m") or []
        rain = hourly.get("precipitation_probability") or []
        parsed = []
        for i, value in enumerate(times):
            try:
                dt = datetime.fromisoformat(str(value))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=now.tzinfo)
                elif now.tzinfo is not None:
                    dt = dt.astimezone(now.tzinfo)
                if dt >= now.replace(minute=0, second=0, microsecond=0):
                    parsed.append((dt,
                                   _number(temperatures[i]) if i < len(temperatures) else None,
                                   _number(rain[i]) if i < len(rain) else None))
            except (ValueError, TypeError):
                continue
        return parsed[:12]

    def _chart(self, hours):
        self._text("Próximas 12 h", 17, 186, 13, self.MUTED)
        samples = hours[::2][:6]
        valid = [temperature for _, temperature, _ in samples if temperature is not None]
        if not valid:
            self._text("Sin pronóstico horario", 17, 220, 14, self.MUTED)
            return
        plot = pygame.Rect(27, 225, 274, 18)
        low, high = min(valid) - 1, max(valid) + 1
        pygame.draw.line(self.surface, self.GRID, (plot.left, plot.bottom),
                         (plot.right, plot.bottom), 1)
        previous = None
        for i, (dt, temperature, _) in enumerate(samples):
            x = round(plot.left + i * plot.width / max(1, len(samples) - 1))
            if temperature is None:
                previous = None
                continue
            y = round(plot.bottom - (temperature - low) * plot.height / (high - low))
            if previous is not None:
                pygame.draw.line(self.surface, self.ACCENT, previous, (x, y), 3)
            pygame.draw.circle(self.surface, self.ACCENT, (x, y), 3)
            self._text(f"{temperature:.0f}°", x - 11, y - 18, 13, self.ACCENT)
            self._text(dt.strftime("%H"), x - 8, 245, 13, self.MUTED)
            previous = (x, y)

    def draw_weather(self, forecast, fetched_at, error, now):
        self._base(now, "weather")
        if not forecast:
            self._center("No se pudo descargar" if error else "Preparando el clima…", 100, 22, bold=True)
            self._center("Se mostrará aquí al recibir los datos.", 147, 15, self.MUTED)
            self._status(False, fetched_at, error, now)
            return
        current = forecast.get("current") or {}
        panel(self.surface, (10, 52, 460, 131), self.palette)
        panel(self.surface, (10, 186, 308, 73), self.palette)
        panel(self.surface, (331, 186, 139, 73), self.palette)
        temperature = _number(current.get("temperature_2m"))
        feels = _number(current.get("apparent_temperature"))
        wind = _number(current.get("wind_speed_10m", current.get("windspeed_10m")))
        raw_code = current.get("weather_code", current.get("weathercode"))
        code = int(raw_code) if _number(raw_code) is not None else None
        temperature_rect = self._text(f"{temperature:.0f}°" if temperature is not None else "—", 15, 52, 66, self.ACCENT, bold=True)
        self._text("C", temperature_rect.right + 4, 94, 24, self.MUTED)
        self._weather_icon(code, bool(current.get("is_day", 1)))
        self._text(WEATHER_LABELS.get(code, "Estado no disponible"),
                   17, 133, 22, max_width=445)
        apparent = f"Sensación {feels:.0f}°" if feels is not None else "Sensación —"
        units = (forecast.get("current_units") or {}).get("wind_speed_10m", "km/h")
        wind_label = f"Viento {wind:.0f} {units}" if wind is not None else "Viento —"
        self._text(apparent + "   ·   " + wind_label, 17, 164, 15, self.MUTED, max_width=445)
        hours = self._hours(forecast, now)
        self._chart(hours)
        pygame.draw.line(self.surface, self.GRID, (324, 190), (324, 253), 1)
        self._text("Prob. de lluvia", 341, 186, 13, self.MUTED)
        # Open-Meteo rainfall probabilities describe the preceding hour.
        probabilities = [rain for dt, _, rain in hours if now < dt <= now + timedelta(hours=6) and rain is not None]
        value = f"{max(probabilities):.0f}%" if probabilities else "—"
        self._text(value, 341, 202, 34, self.ACCENT, bold=True, max_width=123)
        self._text("Máx. en 6 h", 341, 244, 13, self.MUTED)
        self._status(True, fetched_at, error, now)

    def draw_satellite(self, image, fetched_at, error, now):
        self._base(now, "satellite")
        if image is None:
            self._center("No se pudo descargar" if error else "Consultando el satélite…", 103, 22, bold=True)
            self._center("Imagen regional de nubes · NOAA", 150, 15, self.MUTED)
        else:
            width, height = image.get_size()
            if width > 0 and height > 0:
                scale = min(452 / width, 200 / height)
                target = (max(1, round(width * scale)), max(1, round(height * scale)))
                fitted = pygame.transform.smoothscale(image, target)
                self.surface.blit(fitted, ((480 - target[0]) // 2, 53 + (200 - target[1]) // 2))
        self._status(image is not None, fetched_at, error, now, satellite=True)

    def draw_sources(self, now):
        self._base(now, "sources")
        panel(self.surface, (10, 53, 460, 105), self.palette)
        panel(self.surface, (10, 162, 460, 109), self.palette)
        self._text("Clima · Open-Meteo", 15, 56, 18)
        self._text("https://open-meteo.com/", 15, 80, 14, self.ACCENT)
        self._text("Datos meteorológicos · CC BY 4.0", 15, 100, 13)
        self._text("https://creativecommons.org/licenses/by/4.0/", 15, 118, 13, self.ACCENT)
        self._text("Pronóstico de modelos; no es un sensor local.", 15, 138, 13, self.MUTED)
        self._text("GeoColor · CIRA/NOAA", 15, 165, 18)
        self._text("https://satellitemaps.nesdis.noaa.gov/", 15, 190, 14, self.ACCENT)
        self._text("Estados y ciudades · Natural Earth (dominio público)", 15, 211, 13, max_width=449)
        self._text("Xalapa · GeoNames.org (CC BY)", 15, 231, 13)
        self._text("naturalearthdata.com · geonames.org", 15, 250, 13, self.ACCENT)
