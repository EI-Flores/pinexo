"""Projection, metadata, cache failures and preferences tests, offline."""
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import CONFIG
import geo_satellite as geo
from geography import project
from preferences import load_theme, save_theme
JPEG = b"\xff\xd8fixture\xff\xd9padding"

def record():
    return {"key": "20262800100", "captured_at": geo.frame_time("20262800100"), "objectid": 1}
def frame():
    return dict(record(), extent=list(geo.BBOX), crs="EPSG:4326", source="NOAA", image=JPEG)
def catalog():
    return {"features": [{"attributes": {"OBJECTID": 1, "START_TIME": record()["captured_at"] * 1000}}]}

class GeographicTests(unittest.TestCase):
    def test_projection_corners_and_xalapa(self):
        self.assertEqual(project(-121, 42, geo.BBOX, (1000, 1000)), (0, 0))
        self.assertEqual(project(-85, 6, geo.BBOX, (1000, 1000)), (1000, 1000))
        x, y = project(-96.91589, 19.53124, geo.BBOX, (1000, 1000))
        self.assertAlmostEqual(x, 669.0030556, places=5)
        self.assertAlmostEqual(y, 624.1322222, places=5)
        with self.assertRaises(ValueError):
            project(0, 0, [0,0,0,1], (1000, 1000))
    def test_catalog_invalid_ids_and_nan_are_rejected(self):
        value = catalog()
        value["features"].extend([{"attributes":{"objectid":True,"start_time":1000}},
                                  {"attributes":{"objectid":2,"start_time":float("nan")}}])
        self.assertEqual(geo.parse_catalog(value, 8), [record()])
    def test_export_requires_matching_extent(self):
        metadata = {"width":1000,"height":1000,"extent":{"xmin":-118,"ymin":12,"xmax":-86,"ymax":34,"spatialReference":{"wkid":4326}},"href":"https://satellitemaps.nesdis.noaa.gov/sample.jpg"}
        with patch.object(geo,"_json",return_value=metadata), patch.object(geo,"download") as download:
            with self.assertRaises(ValueError):
                geo.export_frame(record())
            download.assert_not_called()
    def test_arcgis_padding_and_bad_jpeg(self):
        self.assertTrue(geo._jpeg(JPEG))
        self.assertFalse(geo._jpeg(b"\xff\xd8unfinished"))
    def test_cache_reuses_frames_and_offline_preserves_age(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            with patch.object(geo,"_json",return_value=catalog()), patch.object(geo,"export_frame",return_value=frame()) as export:
                first=geo.fetch_history(CONFIG,path)
                second=geo.fetch_history(CONFIG,path)
                self.assertEqual(export.call_count,1)
            self.assertEqual(geo.read_history(CONFIG,path)["frames"][0]["extent"],list(geo.BBOX))
            with patch.object(geo,"_json",side_effect=OSError("offline")):
                offline=geo.fetch_history(CONFIG,path)
            self.assertEqual(offline["fetched_at"],second["fetched_at"])
            self.assertIn("warning",offline)
    def test_partial_latest_failure_keeps_previous_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            with patch.object(geo,"_json",return_value=catalog()), patch.object(geo,"export_frame",return_value=frame()):
                geo.fetch_history(CONFIG,path)
            newer={"features":catalog()["features"]+[{"attributes":{"objectid":2,"start_time":record()["captured_at"]*1000+600000}}]}
            with patch.object(geo,"_json",return_value=newer), patch.object(geo,"export_frame",side_effect=OSError("unavailable")):
                event=geo.fetch_history(CONFIG,path)
            self.assertEqual(len(event["frames"]),1)
            self.assertIn("warning",event)
    def test_cache_rejects_different_geographic_extent(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            with patch.object(geo,"_json",return_value=catalog()), patch.object(geo,"export_frame",return_value=frame()):
                geo.fetch_history(CONFIG,path)
            manifest=geo._directory(path)/"manifest.json"
            entry=json.loads(manifest.read_text())
            entry["bbox"][0]=-120
            manifest.write_text(json.dumps(entry))
            self.assertIsNone(geo.read_history(CONFIG,path))

class PreferenceTests(unittest.TestCase):
    def test_default_dark_and_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            self.assertEqual(load_theme(path),"dark")
            self.assertTrue(save_theme(path,"light"))
            self.assertEqual(load_theme(path),"light")
            (path/"preferences.json").write_text('{"theme":"unknown"}')
            self.assertEqual(load_theme(path),"dark")
    def test_read_only_store_does_not_block_theme_use(self):
        with patch("preferences.atomic_write",side_effect=PermissionError("readonly")):
            self.assertFalse(save_theme(Path("unused"),"light"))

if __name__ == "__main__":
    unittest.main()
