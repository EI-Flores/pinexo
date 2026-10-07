"""Offline regression checks for NOAA history parsing and persistent recovery.

Run with: python -m unittest tests.test_satellite_history
The JPEG fixture checks the downloader's container validation only. Actual
JPEG decoding and pixel dimensions are validated separately by the display.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from tests.support import PROJECT
import satellite_data as satellite


class SatelliteHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.config = {"satellite_url": satellite.SOURCE + "500x500.jpg", "satellite_frame_count": 3}
        self.keys = ["20263652350", "20270010000", "20270010010"]
        self.jpeg = b"\xff\xd8" + b"mock-container" + b"\xff\xd9"
        self.calls = []
        self.failures = set()
        self.listing = self.make_listing(self.keys)

    def make_listing(self, keys):
        return "".join('<a href="' + key + '_GOES19-ABI-mex-GEOCOLOR-1000x1000.jpg">frame</a>' for key in keys).encode()

    def download(self, url, limit):
        self.calls.append(url)
        if url in self.failures:
            raise OSError("test connection failure")
        return self.listing if url == satellite.SOURCE else self.jpeg

    def fetch(self, stop=None):
        with patch.object(satellite, "download", self.download):
            return satellite.fetch_history(self.config, self.directory, stop)

    def test_listing_uses_utc_order_and_exact_safe_filenames(self):
        suspicious = b"""
            <a href="../20270010020_GOES19-ABI-mex-GEOCOLOR-1000x1000.jpg">path</a>
            <a href="https://evil.invalid/20270010020_GOES19-ABI-mex-GEOCOLOR-1000x1000.jpg">host</a>
            <a href="20263660000_GOES19-ABI-mex-GEOCOLOR-1000x1000.jpg">invalid day</a>
            <a href="20270012460_GOES19-ABI-mex-GEOCOLOR-1000x1000.jpg">invalid time</a>
            <a href="20270010020_GOES19-ABI-mex-GEOCOLOR-500x500.jpg">wrong size</a>
        """
        records = satellite.parse_listing(self.make_listing(list(reversed(self.keys))) + suspicious + self.listing, 3)
        self.assertEqual([record["key"] for record in records], self.keys)
        self.assertEqual(records[1]["captured_at"] - records[0]["captured_at"], 600)
        self.assertTrue(all(record["url"].startswith(satellite.SOURCE) for record in records))

    def test_first_fetch_round_trip_and_second_fetch_reuses_jpegs(self):
        initial = self.fetch()
        self.assertEqual([frame["key"] for frame in initial["frames"]], self.keys)
        self.assertNotIn("warning", initial)
        self.assertEqual(len(self.calls), 4)
        self.assertTrue(all("1000x1000" in frame["url"] for frame in initial["frames"]))
        recovered = satellite.read_history(self.config, self.directory)
        self.assertEqual(recovered["frames"], initial["frames"])
        self.fetch()
        self.assertEqual(len(self.calls), 5, "Refresh should download the listing only when frames did not change")

    def test_missing_latest_keeps_valid_history_and_reports_incomplete(self):
        self.fetch()
        newest = "20270010020"
        self.listing = self.make_listing(self.keys + [newest])
        self.failures.add(satellite.SOURCE + newest + "_GOES19-ABI-mex-GEOCOLOR-1000x1000.jpg")
        with self.assertLogs(satellite.LOG, level="WARNING"):
            result = self.fetch()
        self.assertEqual([frame["key"] for frame in result["frames"]], self.keys)
        self.assertEqual(result["latest_requested"], newest)
        self.assertIn("warning", result)
        cached = satellite.read_history(self.config, self.directory)
        self.assertIn("warning", cached)
        self.assertEqual(cached["frames"][-1]["captured_at"], result["frames"][-1]["captured_at"])

    def test_offline_index_keeps_original_check_time(self):
        initial = self.fetch()
        self.failures.add(satellite.SOURCE)
        with self.assertLogs(satellite.LOG, level="WARNING"):
            result = self.fetch()
        self.assertEqual(result["fetched_at"], initial["fetched_at"])
        self.assertEqual(result["frames"], initial["frames"])
        self.assertIn("warning", result)

    def test_corrupt_cache_file_is_skipped_then_repaired(self):
        self.fetch()
        cache = satellite._cache_directory(self.directory, satellite.SOURCE)
        bad = cache / (self.keys[-1] + ".jpg")
        bad.write_bytes(b"truncated")
        recovered = satellite.read_history(self.config, self.directory)
        self.assertEqual(len(recovered["frames"]), 2)
        self.assertIn("warning", recovered)
        self.fetch()
        self.assertEqual(bad.read_bytes(), self.jpeg)
        self.assertEqual(len(satellite.read_history(self.config, self.directory)["frames"]), 3)

    def test_cleanup_is_bounded_and_preserves_other_files(self):
        self.fetch()
        cache = satellite._cache_directory(self.directory, satellite.SOURCE)
        unrelated = cache / "user-notes.jpg"
        unrelated.write_bytes(b"leave alone")
        self.listing = self.make_listing(self.keys + ["20270010020", "20270010030"])
        result = self.fetch()
        own_images = [path for path in cache.glob("*.jpg") if path.name != unrelated.name]
        self.assertEqual(len(own_images), 3)
        self.assertEqual([frame["key"] for frame in result["frames"]], ["20270010010", "20270010020", "20270010030"])
        self.assertEqual(unrelated.read_bytes(), b"leave alone")

    def test_manifest_write_failure_preserves_prior_index_and_frames(self):
        original = self.fetch()
        cache = satellite._cache_directory(self.directory, satellite.SOURCE)
        self.listing = self.make_listing(self.keys + ["20270010020"])
        original_write = satellite.atomic_write

        def fail_manifest(path, payload):
            if path.name == "manifest.json":
                raise OSError("test manifest failure")
            return original_write(path, payload)

        with patch.object(satellite, "atomic_write", fail_manifest), self.assertLogs(satellite.LOG, level="WARNING"):
            result = self.fetch()
        self.assertIn("warning", result)
        recovered = satellite.read_history(self.config, self.directory)
        self.assertEqual(recovered["frames"], original["frames"])
        self.assertTrue(all((cache / (key + ".jpg")).exists() for key in self.keys))

    def test_manifest_with_wrong_source_or_url_is_not_reused(self):
        self.fetch()
        manifest = satellite._cache_directory(self.directory, satellite.SOURCE) / "manifest.json"
        entry = json.loads(manifest.read_text())
        entry["source"] = "https://other.invalid/"
        manifest.write_text(json.dumps(entry))
        self.assertIsNone(satellite.read_history(self.config, self.directory))
        entry["source"] = satellite.SOURCE
        for frame in entry["frames"]:
            frame["url"] = "https://other.invalid/unsafe.jpg"
        manifest.write_text(json.dumps(entry))
        self.assertIsNone(satellite.read_history(self.config, self.directory))

    def test_empty_first_download_fails_instead_of_claiming_update(self):
        self.listing = b"<html>No frames yet</html>"
        with self.assertRaises(ValueError):
            self.fetch()
        self.assertIsNone(satellite.read_history(self.config, self.directory))

    def test_cancellation_and_custom_source(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaises(InterruptedError):
            self.fetch(stop)
        self.assertEqual(self.calls, [])
        custom = {"satellite_url": "https://example.org/custom.jpg"}
        self.assertIsNone(satellite.history_source(custom))
        self.assertIsNone(satellite.read_history(custom, self.directory))
        with self.assertRaises(ValueError):
            satellite.fetch_history(custom, self.directory)

    def test_configuration_count_is_bounded(self):
        self.assertEqual(satellite.frame_count({}), 8)
        self.assertEqual(satellite.frame_count({"satellite_frame_count": 1000}), 12)
        self.assertEqual(satellite.frame_count({"satellite_frame_count": 0}), 2)
        self.assertEqual(satellite.frame_count({"satellite_frame_count": "bad"}), 8)
        self.assertEqual(satellite.frame_count({"satellite_frame_count": True}), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
