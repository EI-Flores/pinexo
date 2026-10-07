"""Comprobaciones del menú en una pantalla simulada, sin red ni hardware GPIO."""
import os
import sys
from pathlib import Path
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.support import PROJECT
import pygame
from home_ui import HomeView


class HomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((480, 320))
        cls.now = datetime(2026, 10, 6, 16, 30, tzinfo=ZoneInfo("America/Mexico_City"))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.home = HomeView(self.screen)

    def click(self, name, **kwargs):
        return self.home.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, pos=self.home.buttons[name].center,
            button=1, **kwargs))

    def test_cards_and_theme_buttons(self):
        self.home.draw(self.now)
        self.assertEqual(self.click("weather"), "weather")
        self.assertEqual(self.click("notifications"), "notifications")
        self.assertEqual(self.click("theme"), "theme")
        self.assertIsNone(self.click("weather", touch=True))
        for key, action in ((pygame.K_1, "weather"), (pygame.K_2, "notifications"),
                            (pygame.K_d, "theme"), (pygame.K_ESCAPE, "quit")):
            self.assertEqual(self.home.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=key)), action)

    def test_touch_and_message_return(self):
        pos = self.home.buttons["weather"].center
        touch = pygame.event.Event(pygame.FINGERDOWN, x=pos[0] / 480,
                                   y=pos[1] / 320, finger_id=1)
        self.assertEqual(self.home.handle_event(touch), "weather")
        self.home.draw_notifications(self.now)
        self.assertEqual(self.click("back"), "home")
        self.assertIsNone(self.click("weather"))
        self.assertEqual(self.home.handle_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)), "home")

    def test_layout_and_palettes(self):
        bounds = pygame.Rect(0, 0, 480, 320)
        for rect in self.home.buttons.values():
            self.assertTrue(bounds.contains(rect))
        self.assertFalse(self.home.buttons["weather"].colliderect(self.home.buttons["notifications"]))
        self.assertGreaterEqual(self.home.buttons["weather"].height, 160)
        for theme in ("dark", "light"):
            self.home.set_theme(theme)
            self.assertEqual(self.home.theme, theme)
            self.home.draw(self.now)
            self.home.draw_notifications(self.now)


if __name__ == "__main__":
    unittest.main()
