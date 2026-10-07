"""Vistas del pronóstico diario y de avisos del panel para el LCD de 480×320."""

from __future__ import annotations

from datetime import timedelta

import pygame

from forecast_helpers import compute_rain_alert, daily_rows, future_hourly
from ui import Dashboard, WEATHER_LABELS, _number
from theme import footer_rects, panel


class ForecastDashboard(Dashboard):
    """Amplía las vistas sin cambiar la descarga ni el control de la aplicación."""

    LABELS = {
        "weather": "Clima", "today": "Hoy", "days": "Días",
        "satellite": "Satélite", "sources": "Fuentes", "home": "Inicio",
    }
    WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
    MONTHS = ("ene", "feb", "mar", "abr", "may", "jun",
              "jul", "ago", "sep", "oct", "nov", "dic")

    def __init__(self, surface, title, timezone="America/Mexico_City", rain_threshold=60, theme="dark"):
        super().__init__(surface, title, timezone, theme)
        value = _number(rain_threshold)
        if value is None or not 0 <= value <= 100:
            raise ValueError("El umbral de lluvia debe estar entre 0 y 100")
        self.rain_threshold = value
        self.buttons = footer_rects(self.LABELS)

    def _base(self, now, active):
        super()._base(now, active)

    @staticmethod
    def _temperature(value):
        number = _number(value)
        return f"{number:.0f}°" if number is not None else "—"

    @staticmethod
    def _clock(value):
        return value.strftime("%H:%M") if value is not None else "—"

    def _empty(self, fetched_at, error, now, kind):
        self._center("No se pudo descargar" if error else "Esperando el pronóstico…",
                     103, 20, bold=True)
        self._center("Se mostrará aquí al recibir los datos.", 151, 15, self.MUTED)
        self._status(False, fetched_at, error, now)

    def _rain_bars(self, forecast, now):
        rows = [row for row in future_hourly(forecast, now, max_hours=7)
                if now < row["time"] <= now + timedelta(hours=6)][:6]
        self._text("Prob. de lluvia · intervalo", 15, 145, 13, self.MUTED)
        self._text(f"Umbral {self.rain_threshold:g}%", 350, 145, 13, self.MUTED)
        for index in range(6):
            center = 53 + index * 75
            probability = rows[index]["probability"] if index < len(rows) else None
            text = f"{probability:.0f}%" if probability is not None else "—"
            width = self.fonts[13].size(text)[0]
            self._text(text, center - width // 2, 163, 13, self.ACCENT)
            bar = pygame.Rect(center - 18, 179, 36, 28)
            pygame.draw.rect(self.surface, self.CANVAS, bar, border_radius=3)
            pygame.draw.rect(self.surface, self.BORDER, bar, width=1, border_radius=3)
            if probability is not None and probability > 0:
                height = max(1, round(bar.height * probability / 100))
                fill = pygame.Rect(bar.left, bar.bottom - height, bar.width, height)
                pygame.draw.rect(self.surface, self.ACCENT, fill, border_radius=3)
            if index < len(rows):
                end = rows[index]["time"]
                label = f"{(end - timedelta(hours=1)):%H}–{end:%H}"
            else:
                label = "—"
            width = self.fonts[13].size(label)[0]
            self._text(label, center - width // 2, 208, 13, self.MUTED)
        return rows

    def draw_today(self, forecast, fetched_at, error, now):
        self._base(now, "today")
        if not forecast:
            self._empty(fetched_at, error, now, "today")
            return
        days = daily_rows(forecast, now, include_today=True)
        today = next((row for row in days if row["date"] == now.date()), {})
        self._text("Hoy · " + now.strftime("%d/%m"), 15, 53, 16, bold=True)
        code = _number(today.get("code"))
        label = WEATHER_LABELS.get(int(code) if code is not None else None, "")
        self._text(label, 172, 56, 13, self.MUTED, max_width=293)
        for left, label, field in ((10, "Mínima", "min"), (250, "Máxima", "max")):
            panel(self.surface, (left, 77, 220, 44), self.palette)
            self._text(label, left + 12, 89, 13, self.MUTED)
            self._text(self._temperature(today.get(field)), left + 95, 76, 34, self.ACCENT, bold=True)
        self._text("Amanece " + self._clock(today.get("sunrise")) +
                   "   ·   Anochece " + self._clock(today.get("sunset")),
                   17, 126, 13, self.MUTED, max_width=448)
        rows = self._rain_bars(forecast, now)
        alert = compute_rain_alert(forecast, now, self.rain_threshold)
        if alert:
            panel(self.surface, (10, 224, 460, 34), self.palette,
                  fill=self.WARNING_BG, border=self.WARNING)
            self._text("Aviso del panel: lluvia probable (no oficial)", 17, 224, 13, self.WARNING)
            span = f"Posible entre {alert['start']:%H:%M}–{alert['end']:%H:%M} · hasta {alert['probability']:.0f}%"
            self._text(span, 17, 241, 13, self.WARNING, max_width=448)
        elif any(row["probability"] is not None for row in rows):
            self._text("Ninguna hora disponible supera el umbral", 17, 225, 13, self.MUTED)
            self._text("El aviso del panel no es una alerta oficial.", 17, 241, 13, self.MUTED)
        else:
            self._text("Sin datos de lluvia para emitir un aviso", 17, 225, 13, self.MUTED)
            self._text("El aviso del panel no es una alerta oficial.", 17, 241, 13, self.MUTED)
        self._status(True, fetched_at, error, now)

    def draw_days(self, forecast, fetched_at, error, now):
        self._base(now, "days")
        if not forecast:
            self._empty(fetched_at, error, now, "days")
            return
        days = daily_rows(forecast, now, include_today=False)[:3]
        if not days:
            self._center("Sin pronóstico para próximos días", 104, 20, bold=True)
            self._center("Se actualizará al recibir nuevos datos.", 149, 15, self.MUTED)
        for index, day in enumerate(days):
            top = 55 + index * 66
            panel(self.surface, (10, top, 460, 62), self.palette)
            date = day["date"]
            self._text(f"{self.WEEKDAYS[date.weekday()]} {date.day}",
                       19, top + 7, 19, bold=True, max_width=90)
            self._text(self.MONTHS[date.month - 1], 19, top + 34, 13, self.MUTED)
            code = _number(day.get("code"))
            label = WEATHER_LABELS.get(int(code) if code is not None else None, "Estado —")
            lines = self._wrap(label, 172, 13)
            for line_index, line in enumerate(lines[:2]):
                self._text(line, 116, top + 6 + line_index * 16, 13, self.INK, max_width=172)
            probability = _number(day.get("probability"))
            rain = f"Prob. lluvia {probability:.0f}%" if probability is not None else "Prob. lluvia —"
            self._text(rain, 116, top + 43, 13, self.MUTED)
            temperatures = self._temperature(day.get("min")) + " / " + self._temperature(day.get("max"))
            self._text(temperatures, 307, top + 6, 20, self.ACCENT, bold=True, max_width=155)
            self._text("mín. / máx.", 307, top + 35, 13, self.MUTED)
        self._status(True, fetched_at, error, now)
