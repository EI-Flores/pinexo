"""Cached vector overlays for georeferenced NOAA frames; no GIS dependency."""
from __future__ import annotations

import json
from pathlib import Path
import pygame
from geo_satellite import valid_extent

def project(longitude, latitude, extent, size):
    """WGS84 longitude/latitude to the pixel coordinates of a WGS84 export."""
    if not valid_extent(extent):
        raise ValueError("La imagen no tiene coordenadas geográficas válidas")
    xmin, ymin, xmax, ymax = extent
    return ((longitude - xmin) / (xmax - xmin) * size[0],
            (ymax - latitude) / (ymax - ymin) * size[1])

class MapOverlay:
    def __init__(self, path=None):
        path = path or Path(__file__).with_name("map_data.json")
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if value.get("crs") != "EPSG:4326" or len(value["states"]) != 32:
            raise ValueError("Cartografía local incompleta")
        self.data = value
        self._key = None
        self._canvas = None
        self._projection_key = None
        self._lines = []
        self._cities = []
        self.visible_labels = []
        self.label_rects = []
        pygame.font.init()
        face = pygame.font.match_font("dejavusans", bold=True)
        self.font = pygame.font.Font(face, 13)

    def _prepare(self, extent, size):
        key = (tuple(extent), tuple(size))
        if key == self._projection_key:
            return
        self._lines = [[project(lon, lat, extent, size) for lon, lat in line]
                       for state in self.data["states"] for line in state["lines"] if len(line) > 1]
        self._cities = [(city, project(city["longitude"], city["latitude"], extent, size))
                        for city in self.data["cities"]]
        self._projection_key = key

    def draw(self, surface, rect, frame, zoom, center, palette):
        if frame.get("crs") != "EPSG:4326" or not valid_extent(frame.get("extent")):
            self.visible_labels, self.label_rects = [], []
            return False
        image = frame["image"]
        size, extent = image.get_size(), frame["extent"]
        key = (tuple(extent), size, round(zoom, 6), tuple(round(v, 7) for v in center), palette["ACCENT"])
        if self._key != key:
            self._prepare(extent, size)
            self._canvas = pygame.Surface(rect.size, pygame.SRCALPHA)
            # Reserve the credits and the two bottom status lines.
            area = pygame.Rect(0, 0, rect.width, rect.height - 38)
            self._canvas.set_clip(area)
            scale = min(rect.width / size[0], rect.height / size[1]) * zoom
            def screen(point):
                return (round(rect.width / 2 + (point[0] - center[0] * size[0]) * scale),
                        round(rect.height / 2 + (point[1] - center[1] * size[1]) * scale))
            color = (65, 224, 247, 225) if palette["BG"][0] < 100 else (74, 218, 240, 225)
            for line in self._lines:
                points = [screen(point) for point in line]
                pygame.draw.lines(self._canvas, (2, 12, 20, 170), False, points, 3)
                pygame.draw.lines(self._canvas, color, False, points, 1)
            occupied = [pygame.Rect(4, 4, 153, 26)]
            self.visible_labels, self.label_rects = [], []
            budget = 5
            for step in self.data["label_budget"]:
                if zoom >= step["min_zoom"]:
                    budget = step["max_labels"]
            # Xalapa and the larger cities have priority; zoom adds candidates.
            candidates_by_priority = self._cities
            if zoom >= 2.5:
                # Regional views favour nearby cities as well as population.
                candidates_by_priority = sorted(self._cities, key=lambda row:
                    row[0]["priority"] + 100 * (((row[1][0] / size[0] - center[0]) * zoom) ** 2 +
                                                 ((row[1][1] / size[1] - center[1]) * zoom) ** 2) ** 0.5)
            for city, point in candidates_by_priority:
                if zoom < city["min_zoom"]:
                    continue
                x, y = screen(point)
                if not area.inflate(-12, -12).collidepoint(x, y):
                    continue
                text = self.font.render(city["name"], True, (94, 236, 255) if city.get("highlight") else (241, 251, 255))
                width, height = text.get_size()
                candidates = [(x + 7, y - height // 2), (x - width - 11, y - height // 2),
                              (x - width // 2, y - height - 8), (x - width // 2, y + 7)]
                if city.get("highlight"):
                    candidates = [candidates[2], candidates[0], candidates[3], candidates[1]]
                label = None
                for left, top in candidates:
                    trial = pygame.Rect(left - 3, top - 2, width + 6, height + 4)
                    if area.contains(trial) and not any(trial.inflate(6, 4).colliderect(r) for r in occupied):
                        label = trial
                        break
                if label is None:
                    continue
                pygame.draw.rect(self._canvas, (3, 15, 24, 228), label, border_radius=3)
                self._canvas.blit(text, (label.x + 3, label.y + 2))
                pygame.draw.circle(self._canvas, (3, 15, 24), (x, y), 5 if city.get("highlight") else 4)
                pygame.draw.circle(self._canvas, (65, 234, 255), (x, y), 3 if city.get("highlight") else 2)
                if city.get("highlight"):
                    pygame.draw.circle(self._canvas, (65, 234, 255), (x, y), 6, 1)
                occupied.append(label)
                self.visible_labels.append(city["name"])
                self.label_rects.append(label.move(rect.left, rect.top))
                if len(self.visible_labels) >= budget:
                    break
            self._key = key
        surface.blit(self._canvas, rect)
        return True
