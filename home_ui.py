"""Inicio del panel personal: iconos propios y zonas amplias para el LCD."""

import math
from zoneinfo import ZoneInfo

import pygame

from theme import apply_theme, panel


class HomeView:
    """Menú independiente del módulo del clima, sin servicios de mensajes activos."""

    def __init__(self, surface, title="PiNexo", timezone="America/Mexico_City", theme="dark"):
        self.surface = surface
        self.title = str(title)
        self.timezone = ZoneInfo(timezone)
        self.fonts = {}
        for size in (13, 14, 16, 18, 22, 25, 28):
            self.fonts[size] = pygame.font.SysFont("dejavusans", size)
        self.bold = {size: pygame.font.SysFont("dejavusans", size, bold=True)
                     for size in (16, 18, 22, 25, 28)}
        self.buttons = {
            "weather": pygame.Rect(12, 76, 222, 170),
            "notifications": pygame.Rect(246, 76, 222, 170),
            "theme": pygame.Rect(340, 277, 128, 35),
            "back": pygame.Rect(12, 277, 158, 35),
        }
        self.mode = "home"
        self.set_theme(theme)

    def set_theme(self, mode):
        apply_theme(self, mode)

    def _text(self, text, pos, size=16, color=None, bold=False, max_width=None):
        font = self.bold[size] if bold else self.fonts[size]
        text = str(text)
        if max_width is not None and font.size(text)[0] > max_width:
            while text and font.size(text + "…")[0] > max_width:
                text = text[:-1]
            text += "…"
        rendered = font.render(text, True, color or self.INK)
        self.surface.blit(rendered, pos)
        return rendered.get_rect(topleft=pos)

    def _center(self, text, x, y, size=16, color=None, bold=False):
        font = self.bold[size] if bold else self.fonts[size]
        self._text(text, (round(x - font.size(text)[0] / 2), y), size, color, bold)

    def _base(self, now, subtitle):
        self.surface.fill(self.BG)
        local = now.astimezone(self.timezone) if now.tzinfo else now.replace(tzinfo=self.timezone)
        self._text(self.title, (14, 8), 25, bold=True, max_width=320)
        self._text(subtitle, (15, 42), 14, self.MUTED)
        self._text(local.strftime("%H:%M"), (386, 10), 22, self.ACCENT, bold=True)
        self._text(local.strftime("%d / %m"), (407, 42), 13, self.MUTED)
        pygame.draw.line(self.surface, self.BORDER, (12, 65), (468, 65))
        pygame.draw.line(self.surface, self.ACCENT, (12, 65), (66, 65), 2)
        button = self.buttons["theme"]
        panel(self.surface, button, self.palette)
        self._center("Claro" if self.theme == "dark" else "Oscuro", button.centerx,
                     button.y + 6, 16, self.ACCENT, bold=True)

    def _weather_icon(self, center):
        x, y = center
        sun = (x + 24, y - 16)
        for i in range(8):
            angle = i * math.pi / 4
            start = (sun[0] + round(math.cos(angle) * 25), sun[1] + round(math.sin(angle) * 25))
            end = (sun[0] + round(math.cos(angle) * 32), sun[1] + round(math.sin(angle) * 32))
            pygame.draw.line(self.surface, self.SUN, start, end, 3)
        pygame.draw.circle(self.surface, self.SUN, sun, 18, 3)
        shape = pygame.Surface((110, 70), pygame.SRCALPHA)
        cloud = self.CLOUD
        pygame.draw.circle(shape, cloud, (32, 40), 22)
        pygame.draw.circle(shape, cloud, (57, 27), 28)
        pygame.draw.circle(shape, cloud, (83, 40), 20)
        pygame.draw.rect(shape, cloud, (30, 38, 55, 22), border_radius=5)
        self.surface.blit(shape, (x - 57, y - 18))
        # Contorno sencillo para mantener el icono legible a baja resolución.
        pygame.draw.line(self.surface, self.ACCENT, (x - 30, y + 41), (x + 27, y + 41), 3)
        for offset in (-19, 4, 27):
            pygame.draw.line(self.surface, self.ACCENT, (x + offset, y + 48),
                             (x + offset - 4, y + 56), 3)

    def _bell_icon(self, center):
        x, y = center
        color = self.ACCENT
        pygame.draw.circle(self.surface, color, (x, y - 27), 5, 2)
        pygame.draw.arc(self.surface, color, (x - 28, y - 28, 56, 57), 0, math.pi, 4)
        pygame.draw.line(self.surface, color, (x - 28, y), (x - 28, y + 21), 4)
        pygame.draw.line(self.surface, color, (x + 27, y), (x + 27, y + 21), 4)
        pygame.draw.lines(self.surface, color, False,
                          ((x - 28, y + 19), (x - 36, y + 32),
                           (x + 36, y + 32), (x + 27, y + 19)), 4)
        pygame.draw.arc(self.surface, color, (x - 9, y + 25, 18, 22), math.pi, 2 * math.pi, 3)
        pygame.draw.circle(self.surface, self.WARNING, (x + 31, y - 18), 8)

    def draw(self, now):
        self.mode = "home"
        self._base(now, "Panel personal · Inicio")
        for name in ("weather", "notifications"):
            rect = self.buttons[name]
            panel(self.surface, rect, self.palette)
        climate = self.buttons["weather"]
        notifications = self.buttons["notifications"]
        self._weather_icon((climate.centerx, 129))
        self._bell_icon((notifications.centerx, 139))
        self._center("Clima", climate.centerx, 193, 25, bold=True)
        self._center("Xalapa · pronóstico y satélite", climate.centerx, 224, 13, self.MUTED)
        self._center("Notificaciones", notifications.centerx, 193, 18, bold=True)
        self._center("Próximamente", notifications.centerx, 222, 14, self.WARNING)
        self._text("1 Clima  ·  2 Notificaciones", (14, 288), 13, self.MUTED)

    def draw_notifications(self, now):
        self.mode = "notifications"
        self._base(now, "Notificaciones")
        panel(self.surface, pygame.Rect(12, 77, 456, 185), self.palette)
        self._bell_icon((240, 119))
        self._center("Próximamente", 240, 168, 22, self.WARNING, bold=True)
        self._center("Este espacio está preparado para avisos.", 240, 205, 16)
        self._center("Las cuentas y los mensajes aún no están conectados.",
                     240, 235, 13, self.MUTED)
        rect = self.buttons["back"]
        panel(self.surface, rect, self.palette)
        self._center("Volver a Inicio", rect.centerx, rect.y + 6, 16, self.ACCENT, bold=True)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_d:
                return "theme"
            if event.key in (pygame.K_1, pygame.K_KP1):
                return "weather"
            if event.key in (pygame.K_2, pygame.K_KP2):
                return "notifications"
            if event.key == pygame.K_ESCAPE:
                return "home" if self.mode == "notifications" else "quit"
            return None
        if event.type == pygame.MOUSEBUTTONDOWN:
            # SDL también emite mouse para algunos eventos táctiles: no duplicar.
            if getattr(event, "touch", False) or getattr(event, "button", None) != 1:
                return None
            pos = event.pos
        elif event.type == pygame.FINGERDOWN:
            width, height = self.surface.get_size()
            pos = (round(event.x * width), round(event.y * height))
        else:
            return None
        if self.buttons["theme"].collidepoint(pos):
            return "theme"
        if self.mode == "notifications":
            return "home" if self.buttons["back"].collidepoint(pos) else None
        for name in ("weather", "notifications"):
            if self.buttons[name].collidepoint(pos):
                return name
        return None
