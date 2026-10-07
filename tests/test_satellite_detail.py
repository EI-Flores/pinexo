"""Offline checks for exact satellite scenes and the bounded detail cache."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from tests.support import PROJECT
import satellite_detail as detail


def jpeg(width, height):
    # Minimal frame header fixture, not an image intended for the GUI decoder.
    header = bytes([8]) + height.to_bytes(2, "big") + width.to_bytes(2, "big")
    header += bytes([3, 1, 0x11, 0, 2, 0x11, 0, 3, 0x11, 0])
    return b"\xff\xd8\xff\xc0" + (len(header) + 2).to_bytes(2, "big") + header + b"\xff\xd9"


class DetailTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="satellite-detail-")
        self.cache = Path(self.temporary.name).resolve()
        self.key = "20262791520"
        self.request = {"request_token": 7, "key": self.key,
                        "captured_at": detail.frame_time(self.key),
                        "extent": [-100, 18, -95, 21.594595]}
        self.wanted = detail._request(self.request)
        self.stop = threading.Event()
        self.calls = []
        self.catalog = {"features": [{"attributes": {
            "objectid": 31, "start_time": self.request["captured_at"] * 1000}}]}
        self.metadata = {"width": 800, "height": 575,
                         "extent": dict(zip(("xmin", "ymin", "xmax", "ymax"), self.wanted["extent"])),
                         "href": "https://satellitemaps.nesdis.noaa.gov/arcgis/rest/directories/detail.jpg"}
        self.metadata["extent"]["spatialReference"] = {"wkid": 4326}
        self.image = jpeg(800, 575)

    def tearDown(self):
        self.temporary.cleanup()

    def download(self, url, limit):
        self.calls.append((url, limit))
        if "/query?" in url:
            return json.dumps(self.catalog).encode()
        if "/exportImage?" in url:
            return json.dumps(self.metadata).encode()
        return self.image

    def fetch(self):
        with patch.object(detail, "download", self.download):
            return detail.fetch_detail(self.request, self.cache, self.stop)

    def test_export_locks_exact_scene_and_cache_reuses_new_token(self):
        event = self.fetch()
        self.assertEqual(event["kind"], "satellite_detail")
        self.assertEqual(event["request_token"], 7)
        self.assertEqual(event["frames"][0]["key"], self.key)
        self.assertEqual(len(self.calls), 3)
        query = parse_qs(urlparse(self.calls[0][0]).query)
        stamp = int(self.request["captured_at"] * 1000)
        self.assertEqual(query["time"], [f"{stamp},{stamp + 59999}"])
        export = parse_qs(urlparse(self.calls[1][0]).query)
        self.assertEqual(json.loads(export["mosaicRule"][0])["lockRasterIds"], [31])
        self.assertEqual(export["time"], [str(stamp)])
        self.assertEqual(export["size"], ["800,575"])
        self.assertEqual(export["imageSR"], ["4326"])
        newer = dict(self.request, request_token=8)
        with patch.object(detail, "download", side_effect=AssertionError("cache made a request")):
            cached = detail.fetch_detail(newer, self.cache)
        self.assertEqual(cached["request_token"], 8)
        self.assertEqual(cached["fetched_at"], event["fetched_at"])

    def test_cache_rejects_different_extent_and_changed_image(self):
        self.fetch()
        changed = dict(self.request, extent=[-101, 18, -96, 21.594595])
        self.assertIsNone(detail.read_detail(changed, self.cache))
        folder = detail._directory(self.cache)
        (folder / "detail.jpg").write_bytes(self.image + b"padding")
        self.assertIsNone(detail.read_detail(self.request, self.cache))

    def test_failed_new_detail_preserves_previous_cache(self):
        self.fetch()
        original = dict(self.request)
        self.request = dict(self.request, request_token=9, extent=[-101, 18, -96, 21.594595])
        self.metadata["extent"]["xmin"] = -999
        with self.assertRaises(ValueError):
            self.fetch()
        self.assertIsNotNone(detail.read_detail(original, self.cache))

    def test_wrong_minute_never_substitutes_latest_frame(self):
        self.catalog["features"][0]["attributes"]["start_time"] -= 600_000
        with self.assertRaises(ValueError):
            self.fetch()
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(detail.read_detail(self.request, self.cache))

    def test_mismatched_extent_and_reference_rejected_before_image(self):
        self.metadata["extent"]["xmin"] -= .01
        with self.assertRaises(ValueError):
            self.fetch()
        self.assertEqual(len(self.calls), 2)
        self.metadata["extent"]["xmin"] += .01
        self.metadata["extent"]["spatialReference"]["wkid"] = 3857
        with self.assertRaises(ValueError):
            self.fetch()
        self.assertEqual(len(self.calls), 4)

    def test_bad_image_dimensions_and_remote_host_rejected(self):
        self.image = jpeg(900, 575)
        with self.assertRaises(ValueError):
            self.fetch()
        self.image = jpeg(800, 575)
        self.metadata["href"] = "https://example.org/image.jpg"
        with self.assertRaises(ValueError):
            self.fetch()
        self.assertEqual(len(self.calls), 5)

    def test_invalid_requests_do_not_download(self):
        invalid = [dict(self.request, request_token=True),
                   dict(self.request, key="../../image"),
                   dict(self.request, captured_at=self.request["captured_at"] + 60),
                   dict(self.request, extent=[-180, 18, -95, 20]),
                   dict(self.request, extent=[-100, 18, -100, 20]),
                   dict(self.request, extent=[-100, 18, -95, float("nan")]),
                   dict(self.request, extent=[-100, 18, -95, 18.00001])]
        with patch.object(detail, "download", side_effect=AssertionError("bad request downloaded")):
            for request in invalid:
                with self.subTest(request=request), self.assertRaises(ValueError):
                    detail.fetch_detail(request, self.cache)

    def test_cancellation_between_downloads_stops_and_does_not_write(self):
        self.stop.set()
        with self.assertRaises(InterruptedError):
            self.fetch()
        self.assertEqual(self.calls, [])
        self.stop.clear()
        original = self.download
        def stop_after_catalog(url, limit):
            response = original(url, limit)
            self.stop.set()
            return response
        with patch.object(detail, "download", stop_after_catalog), self.assertRaises(InterruptedError):
            detail.fetch_detail(self.request, self.cache, self.stop)
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(detail.read_detail(self.request, self.cache))

    def test_one_cache_pair_survives_multiple_viewports(self):
        self.fetch()
        self.request = dict(self.request, request_token=10, extent=[-101, 18, -96, 21.594595])
        self.wanted = detail._request(self.request)
        self.metadata["extent"]["xmin"] = -101
        self.metadata["extent"]["xmax"] = -96
        self.fetch()
        files = {path.name for path in detail._directory(self.cache).iterdir()}
        self.assertEqual(files, {"detail.jpg", "detail.json"})


if __name__ == "__main__":
    unittest.main()
