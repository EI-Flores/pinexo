"""Failure-oriented verification for the dashboard cache and network worker."""
import copy
import json
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import CONFIG, FORECAST
import data
import satellite_data
import geo_satellite



class CacheAndNetworkTests(unittest.TestCase):
    def test_other_location_cache_is_not_used(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            entry = {"location": [0, 0, CONFIG["timezone"]], "fetched_at": 1, "forecast": FORECAST}
            (directory / "weather.json").write_text(json.dumps(entry), encoding="utf-8")
            self.assertEqual(data.read_cache(CONFIG, directory), [])

    def test_bad_download_never_overwrites_last_valid_weather(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            with patch.object(data, "download", return_value=json.dumps(FORECAST).encode()):
                data.fetch_weather(CONFIG, directory)
            original = (directory / "weather.json").read_bytes()
            with patch.object(data, "download", return_value=b'{"error":true,"reason":"bad reply"}'):
                with self.assertRaises(ValueError):
                    data.fetch_weather(CONFIG, directory)
            self.assertEqual((directory / "weather.json").read_bytes(), original)
            self.assertEqual(data.read_cache(CONFIG, directory)[0]["forecast"]["current"]["temperature_2m"], 22)

    def test_missing_measurements_are_allowed_but_broken_arrays_are_rejected(self):
        forecast = copy.deepcopy(FORECAST)
        forecast["current"]["temperature_2m"] = None
        forecast["hourly"]["temperature_2m"][0] = None
        data.validate_forecast(forecast)
        forecast["hourly"]["precipitation_probability"].pop()
        with self.assertRaises(ValueError):
            data.validate_forecast(forecast)

    def test_corrupt_cache_does_not_crash_startup(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "weather.json").write_text("unfinished", encoding="utf-8")
            (directory / "satellite.json").write_text("{}", encoding="utf-8")
            self.assertEqual(data.read_cache(CONFIG, directory), [])

    def test_read_only_cache_does_not_discard_received_weather(self):
        with patch.object(data, "download", return_value=json.dumps(FORECAST).encode()), patch.object(data, "atomic_write", side_effect=PermissionError("read-only")):
            result = data.fetch_weather(CONFIG, Path("unused"))
            self.assertEqual(result["forecast"]["current"]["temperature_2m"], 22)

    def test_worker_continues_other_provider_after_failure(self):
        stop = threading.Event()
        events = queue.Queue()
        def satellite(*_):
            stop.set()
            return {"kind": "satellite_history", "frames": [], "fetched_at": 1}
        with patch.object(data, "fetch_weather", side_effect=OSError("offline")), patch.object(geo_satellite, "fetch_history", side_effect=satellite):
            data.run_downloads(CONFIG, Path("unused"), events, stop)
        self.assertIn("error", events.get_nowait())
        self.assertEqual(events.get_nowait()["kind"], "satellite_history")


if __name__ == "__main__":
    unittest.main()
