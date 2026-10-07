"""Paletas y marcos ligeros para el LCD, sin efectos ni recursos externos."""

import pygame


PALETTES = {
    "dark": {
        "BG": (3, 12, 20), "PANEL": (8, 23, 35), "INK": (222, 244, 250),
        "MUTED": (139, 185, 199), "ACCENT": (22, 214, 242), "ACCENT_INK": (2, 18, 26),
        "GRID": (24, 69, 86), "BORDER": (36, 112, 135),
        "WARNING": (255, 198, 112), "WARNING_BG": (43, 28, 14),
        "SUN": (255, 205, 99), "CLOUD": (42, 114, 139),
        "CANVAS": (12, 20, 27), "IMAGE_INK": (236, 249, 255),
        "IMAGE_WARNING": (255, 211, 146), "OVERLAY": (5, 17, 26, 228),
    },
    "light": {
        "BG": (232, 243, 249), "PANEL": (249, 253, 255), "INK": (16, 49, 65),
        "MUTED": (58, 89, 106), "ACCENT": (0, 119, 146), "ACCENT_INK": (255, 255, 255),
        "GRID": (182, 209, 222), "BORDER": (61, 137, 158),
        "WARNING": (140, 68, 12), "WARNING_BG": (255, 239, 215),
        "SUN": (181, 119, 6), "CLOUD": (101, 160, 181),
        "CANVAS": (12, 20, 27), "IMAGE_INK": (236, 249, 255),
        "IMAGE_WARNING": (255, 211, 146), "OVERLAY": (5, 17, 26, 228),
    },
}


def palette(mode="dark"):
    """Devuelve una copia para que cada vista conserve sus propios colores."""
    if not isinstance(mode, str) or mode not in PALETTES:
        raise ValueError("El tema debe ser 'dark' o 'light'")
    return dict(PALETTES[mode])


def apply_theme(view, mode):
    colors = palette(mode)
    view.theme = mode
    view.palette = colors
    for name, color in view.palette.items():
        setattr(view, name, color)
    # Alias conservado para las vistas anteriores; ahora representa un panel.
    view.WHITE = view.PANEL


def footer_rects(names):
    names = list(names)
    gap, margin = 4, 5
    width = (480 - 2 * margin - gap * (len(names) - 1)) // len(names)
    return {name: pygame.Rect(margin + index * (width + gap), 278, width, 36)
            for index, name in enumerate(names)}


def panel(surface, rect, colors, active=False, fill=None, border=None):
    """Panel con líneas de esquina: solo rectángulos y segmentos pequeños."""
    rect = pygame.Rect(rect)
    fill = fill or (colors["ACCENT"] if active else colors["PANEL"])
    border = border or (colors["ACCENT"] if active else colors["BORDER"])
    pygame.draw.rect(surface, fill, rect, border_radius=4)
    pygame.draw.rect(surface, border, rect, width=1, border_radius=4)
    if not active:
        color = border if border != colors["BORDER"] else colors["ACCENT"]
        for x, y, dx, dy in ((rect.left, rect.top, 1, 1),
                              (rect.right - 1, rect.top, -1, 1),
                              (rect.left, rect.bottom - 1, 1, -1),
                              (rect.right - 1, rect.bottom - 1, -1, -1)):
            pygame.draw.line(surface, color, (x + dx * 2, y), (x + dx * 8, y))
            pygame.draw.line(surface, color, (x, y + dy * 2), (x, y + dy * 8))
