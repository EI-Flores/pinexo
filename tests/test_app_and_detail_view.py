"""Integration checks for home routing and regional satellite detail."""
import io
import json
import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from tests.support import CONFIG, FORECAST, FixedDatetime
import pygame
import app
import home_ui
import forecast_ui
import satellite_ui
import geo_satellite
from preferences import save_theme, load_theme


class DetailViewTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.font.init()
        self.surface = pygame.display.set_mode((480, 320))
        self.view = satellite_ui.SatelliteView(self.surface)
        frame = {"key": "20262800200", "captured_at": geo_satellite.frame_time("20262800200"),
                 "extent": list(geo_satellite.BBOX), "crs": "EPSG:4326", "source": "NOAA",
                 "image": pygame.Surface((1000, 1000))}
        frame["image"].fill((5, 10, 15))
        self.view.set_frames([frame], frame["captured_at"])
        self.view._action("veracruz")
        self.view._set_zoom(10)

    def tearDown(self):
        pygame.quit()

    def request(self):
        self.assertIsNone(self.view.poll_detail(1))
        request = self.view.poll_detail(2.3)
        self.assertIsNotNone(request)
        return request

    def detail(self, request):
        image = pygame.Surface((800, 575))
        image.fill((50, 100, 200))
        return {**request, "image": image, "crs": "EPSG:4326", "source": "NOAA"}

    def test_zoom_pauses_and_debounces_one_request(self):
        self.assertEqual(self.view.zoom, 10)
        self.assertFalse(self.view.playing)
        request = self.request()
        self.assertTrue(self.view.expects_detail(request["request_token"]))
        self.assertIsNone(self.view.poll_detail(200))
        self.view._set_zoom(100)
        self.assertEqual(self.view.zoom, 10)

    def test_stale_token_and_capture_cannot_replace_scene(self):
        request = self.request()
        self.view._pan(30, 0)
        self.assertFalse(self.view.expects_detail(request["request_token"]))
        with self.assertRaises(ValueError):
            self.view.set_detail({**self.detail(request), "key": "20262800100"})
        self.assertIsNone(self.view.detail)

    def test_detail_geometry_and_reuse(self):
        request = self.request()
        self.view.set_detail(self.detail(request))
        self.assertEqual(self.view.detail_status, "ready")
        canvas = self.view._render_detail()
        self.assertEqual(canvas.get_size(), (370, 266))
        for point in ((0, 0), (369, 265), (185, 133)):
            self.assertEqual(canvas.get_at(point).a, 255)
            self.assertTrue(all(abs(a - b) <= 3 for a, b in zip(canvas.get_at(point)[:3], (50, 100, 200))))
        self.assertIsNone(self.view.poll_detail(10))
        self.view._set_zoom(8)
        self.assertIsNone(self.view._render_detail())
        self.view._set_zoom(10)
        self.assertIsNotNone(self.view._render_detail())

    def test_failure_preserves_base_and_limits_new_detail(self):
        request = self.request()
        original = self.view._current()
        self.view.detail_failed(2.3)
        self.assertIs(self.view._current(), original)
        self.assertIsNone(self.view.poll_detail(60))
        with self.assertRaises(ValueError):
            self.view.set_detail({**self.detail(request), "image": pygame.Surface((801, 575))})
        self.assertIsNone(self.view.detail)
        retry = self.view.poll_detail(63)
        self.assertIsNotNone(retry)
        self.assertNotEqual(retry["request_token"], request["request_token"])
        self.assertFalse(self.view.expects_detail(request["request_token"]))

    def test_new_scene_rejects_old_patch(self):
        request = self.request()
        frame = {**self.view._current(), "key": "20262800210", "captured_at": geo_satellite.frame_time("20262800210")}
        self.view.set_frames([frame], frame["captured_at"])
        self.assertFalse(self.view.expects_detail(request["request_token"]))
        self.assertIsNone(self.view.poll_detail(3))
        new_request = self.view.poll_detail(4.3)
        self.assertEqual(new_request["key"], frame["key"])
        self.assertNotEqual(new_request["request_token"], request["request_token"])

    def test_leaving_during_drag_cancels_pending_and_drag(self):
        request = self.request()
        self.view.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(100, 100), button=1))
        self.assertIsNotNone(self.view._drag)
        self.view.poll_detail(3, enabled=False)
        self.assertIsNone(self.view._drag)
        self.assertFalse(self.view.expects_detail(request["request_token"]))
        self.assertIsNone(self.view.poll_detail(4))
        self.assertIsNotNone(self.view.poll_detail(5.3))

    def test_playback_uses_consistent_base_sequence(self):
        request = self.request()
        self.view.set_detail(self.detail(request))
        self.view._action("play")
        self.assertTrue(self.view.playing)
        self.assertIsNone(self.view._render_detail())
        self.assertIsNone(self.view.poll_detail(4))
        self.assertFalse(self.view.expects_detail(request["request_token"]))


class AppRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="app-routing-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.config_path = self.directory / "config.json"
        self.config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
        self.cache = self.directory / "pi-clima"
        self.environment = patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.directory)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(pygame.quit)

    def history_fixture(self):
        buffer = io.BytesIO()
        image = pygame.Surface((1000, 1000))
        image.fill((5, 10, 15))
        pygame.image.save(image, buffer, "fixture.jpg")
        key = "20262800200"
        captured = geo_satellite.frame_time(key)
        frame = {"key": key, "captured_at": captured, "extent": list(geo_satellite.BBOX),
                 "crs": "EPSG:4326", "source": "NOAA", "image": buffer.getvalue()}
        return {"kind": "satellite_history", "frames": [frame], "fetched_at": captured}

    def test_home_weather_detail_notifications_and_theme(self):
        key = lambda value: pygame.event.Event(pygame.KEYDOWN, key=value)
        click = lambda point: pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=point, button=1)
        finger = lambda point: pygame.event.Event(pygame.FINGERDOWN, x=point[0]/480, y=point[1]/320, finger_id=1)
        synthetic = lambda point: pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=point, button=1, touch=True)
        batches = [[], [click((120, 130))], [key(pygame.K_4)], [key(pygame.K_v)],
                   [key(pygame.K_EQUALS)] * 8, [], [], [], [], [], [key(pygame.K_d)],
                   [finger((438, 296)), synthetic((438, 296))], [click((350, 130))],
                   [key(pygame.K_ESCAPE)], [finger((400, 296)), synthetic((400, 296))],
                   [key(pygame.K_1)], [key(pygame.K_ESCAPE)], [key(pygame.K_ESCAPE)]]
        moments = [0]
        shown = []
        views = []
        requests = []
        cache = self.cache
        save_theme(cache, "dark")
        history = self.history_fixture()
        weather = {"kind": "weather", "forecast": FORECAST,
                   "fetched_at": history["fetched_at"]}
        real_home, real_sat = home_ui.HomeView, satellite_ui.SatelliteView
        def make_home(*args, **kwargs):
            view = real_home(*args, **kwargs)
            for name in ("draw", "draw_notifications"):
                original = getattr(view, name)
                def draw(now, original=original, name=name):
                    shown.append((name, view.theme))
                    return original(now)
                setattr(view, name, draw)
            return view
        def make_sat(*args, **kwargs):
            view = real_sat(*args, **kwargs)
            views.append(view)
            original = view.draw
            def draw(*args):
                shown.append(("satellite", view.theme))
                return original(*args)
            view.draw = draw
            return view
        class FakeWorker:
            def __init__(self, cache, events, stop):
                self.events = events
            def start(self):
                pass
            def request(self, request):
                requests.append(request)
                buffer = io.BytesIO()
                image = pygame.Surface((800, 575))
                image.fill((50, 100, 200))
                pygame.image.save(image, buffer, "detail.jpg")
                frame = {**request, "crs": "EPSG:4326", "source": "NOAA", "image": buffer.getvalue()}
                self.events.put({"kind": "satellite_detail", "request_token": -1, "error": "stale"})
                self.events.put({"kind": "satellite_detail", "request_token": request["request_token"], "frames": [frame]})
        def wait(_):
            moments[0] += 0.5
            # A paused high-zoom view must survive the weather rotation timer.
            if len(batches) == 9:
                moments[0] += 60
        try:
            with patch.object(sys, "argv", ["app.py", "--windowed", "--config", str(self.config_path)]), \
                 patch.object(app.threading, "Thread"), \
                 patch.object(app, "read_cache", return_value=[weather]), \
                 patch.object(app, "read_geographic_history", return_value=history), \
                 patch.object(app, "read_history", return_value=None), \
                 patch.object(app, "datetime", FixedDatetime), \
                 patch("urllib.request.urlopen", side_effect=AssertionError("Tests must stay offline")), \
                 patch("detail_worker.DetailWorker", FakeWorker), \
                 patch.object(home_ui, "HomeView", side_effect=make_home), \
                 patch.object(satellite_ui, "SatelliteView", side_effect=make_sat), \
                 patch.object(app.time, "monotonic", side_effect=lambda: moments[0]), \
                 patch.object(pygame.time, "wait", side_effect=wait), \
                 patch.object(pygame.event, "get", side_effect=lambda: batches.pop(0)):
                self.assertEqual(app.main(), 0)
            self.assertFalse(batches)
            self.assertEqual(shown[0], ("draw", "dark"))
            self.assertIn(("draw_notifications", "light"), shown)
            self.assertIn(("draw", "dark"), shown)
            self.assertEqual(len(requests), 1)
            self.assertEqual(views[0].zoom, 10)
            self.assertFalse(views[0].playing)
            self.assertIsNotNone(views[0].detail)
            self.assertEqual(load_theme(cache), "dark")
        finally:
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
