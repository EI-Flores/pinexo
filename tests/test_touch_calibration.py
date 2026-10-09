"""Verify affine fitting, quality reporting, and stationary contact collection."""
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import touch_calibration as touch


class TouchCalibrationMathTests(unittest.TestCase):
    def contacts(self, observed=None):
        positions = observed if observed is not None else touch.TARGETS
        return [{"observed_pixels": list(point), "duration_seconds": 0.8,
                 "event_samples": 12, "p90_radius_pixels": 1.0} for point in positions]

    def test_fit_recovers_scale_offset_and_cross_axis_terms(self):
        observed = [(0.5, 0.5), (0.15, 0.2), (0.8, 0.2), (0.8, 0.8), (0.15, 0.8)]
        expected = (1.2, 0.05, -0.11, -0.03, 1.3, -0.15)
        actual, condition = touch.fit_affine(observed, [touch.transform(expected, point) for point in observed])
        for left, right in zip(actual, expected):
            self.assertAlmostEqual(left, right, places=10)
        self.assertLess(condition, 1000)

    def test_correction_is_composed_after_the_current_sensor_matrix(self):
        current = (0, 1, 0, -1, 0, 1)
        correction = (-1.2, 0, 1.1, 0, 1.3, -0.1)
        composed = touch.compose(correction, current)
        for raw in ((0, 0), (0.15, 0.82), (1, 1)):
            expected = touch.transform(correction, touch.transform(current, raw))
            for actual, target in zip(touch.transform(composed, raw), expected):
                self.assertAlmostEqual(actual, target, places=12)

    def test_degenerate_collinear_and_clustered_points_are_rejected(self):
        for points in ([(0.5, 0.5)] * 5,
                       [(i / 5, i / 5) for i in range(5)],
                       [(0.5, 0.5), (0.501, 0.5), (0.5, 0.501), (0.501, 0.501), (0.5005, 0.5002)]):
            with self.subTest(points=points), self.assertRaises(touch.CalibrationError):
                touch.fit_affine(points, [(x / 480, y / 320) for x, y in touch.TARGETS])

    def test_missing_contacts_and_nonfinite_samples_are_rejected(self):
        with self.assertRaises(touch.CalibrationError):
            touch.fit_affine([(0, 0)] * 4, [(0, 0)] * 4)
        with self.assertRaises(touch.CalibrationError):
            touch.fit_affine([(0, 0)] * 4 + [(math.nan, 0)], [(0, 0)] * 5)

    def test_contact_median_ignores_settling_and_release_slip(self):
        samples = [(0, 10, 10), (0.02, 15, 15)]
        samples += [(i / 100, 100 + (i % 3 - 1), 120 + (i % 3 - 1)) for i in range(10, 70, 5)]
        samples += [(0.76, 240, 280)]
        summary = touch.summarize_contact(samples, 0.8)
        self.assertAlmostEqual(summary["observed_pixels"][0], 100, delta=1)
        self.assertAlmostEqual(summary["observed_pixels"][1], 120, delta=1)
        self.assertEqual(summary["settled_samples"], 12)
        self.assertEqual(summary["quality_reasons"], [])

    def test_low_quality_contact_is_recorded_for_diagnosis(self):
        for samples, duration in (([(0, 10, 10)], 0.8),
                                  ([(0, 10, 10)] * 3, 0.1),
                                  ([(0, 10, 10)] * 3, 3.0),
                                  ([(0.1 * i, 40 * i, 20 * i) for i in range(8)], 0.8)):
            with self.subTest(samples=samples, duration=duration):
                summary = touch.summarize_contact(samples, duration)
                self.assertTrue(summary["quality_reasons"])
                self.assertEqual(summary["event_samples"], len(samples))
                self.assertEqual(summary["duration_seconds"], duration)
                self.assertTrue(all(math.isfinite(value) for value in summary["observed_pixels"]))

    def test_missing_or_nonfinite_contact_is_rejected(self):
        for samples, duration in (([], 0.8), ([(0, math.nan, 10)], 0.8),
                                  ([(0, 10)], 0.8), ([(0, 10, 10)], math.nan),
                                  ([(0, 10, 10)], -0.1)):
            with self.subTest(samples=samples, duration=duration), self.assertRaises(touch.CalibrationError):
                touch.summarize_contact(samples, duration)

    def test_identity_positions_preserve_current_matrix_and_mark_unverified(self):
        current = [0, 1, 0, -1, 0, 1]
        report = touch.build_report(self.contacts(), {"matrix": current}, "mouse")
        self.assertEqual(report["status"], "proposed")
        self.assertFalse(report["applied"])
        self.assertFalse(report["active_matrix_verified"])
        for actual, expected in zip(report["proposed_matrix"], current):
            self.assertAlmostEqual(actual, expected, places=10)
        self.assertLess(report["maximum_residual_pixels"], 1e-8)

    def test_wrong_point_and_windowed_test_never_emit_proposal(self):
        contacts = self.contacts()
        contacts[0]["observed_pixels"] = [300, 240]
        invalid = touch.build_report(contacts, {"matrix": [1, 0, 0, 0, 1, 0]}, "mouse")
        self.assertEqual(invalid["status"], "invalid")
        self.assertGreater(invalid["maximum_residual_pixels"], 10)
        self.assertNotIn("proposed_matrix", invalid)
        preview = touch.build_report(self.contacts(), {"matrix": [1, 0, 0, 0, 1, 0]}, "mouse", True)
        self.assertEqual(preview["status"], "invalid")
        self.assertNotIn("proposed_matrix", preview)

    def test_report_corrects_margin_error_without_losing_sensor_orientation(self):
        shrink = (0.75, 0, 0.125, 0, 0.8, 0.1)
        normalized_targets = [(x / 480, y / 320) for x, y in touch.TARGETS]
        normalized_observed = [touch.transform(shrink, point) for point in normalized_targets]
        pixels = [(x * 480, y * 320) for x, y in normalized_observed]
        report = touch.build_report(self.contacts(pixels), {"matrix": [0, 1, 0, -1, 0, 1]}, "mouse")
        self.assertEqual(report["status"], "proposed")
        self.assertGreater(report["original_rms_error_pixels"], 10)
        self.assertLess(report["fitted_rms_error_pixels"], 1e-8)
        for observed, target in zip(normalized_observed, normalized_targets):
            raw = (1 - observed[1], observed[0])
            for actual, expected in zip(touch.transform(report["proposed_matrix"], raw), target):
                self.assertAlmostEqual(actual, expected, places=10)

    def test_bad_contact_metadata_prevents_proposal(self):
        contacts = self.contacts()
        contacts[1]["event_samples"] = 1
        report = touch.build_report(contacts, {"matrix": [1, 0, 0, 0, 1, 0]}, "mouse")
        self.assertEqual(report["status"], "invalid")
        self.assertNotIn("proposed_matrix", report)

    def test_quality_reasons_prevent_proposal_even_with_otherwise_valid_metadata(self):
        contacts = self.contacts()
        contacts[0]["quality_reasons"] = ["Insufficient retained samples."]
        report = touch.build_report(contacts, {"matrix": [1, 0, 0, 0, 1, 0]}, "mouse")
        self.assertEqual(report["status"], "invalid")
        self.assertNotIn("proposed_matrix", report)

    def test_namespaced_config_and_duplicate_profiles(self):
        profile = '<device category="ADS7846 Touchscreen"><calibrationMatrix>0 1 0 -1 0 1</calibrationMatrix></device>'
        prefix = '<openbox_config xmlns="http://openbox.org/3.4/rc"><touch deviceName="ADS7846 Touchscreen" mapToOutput="SPI-1" mouseEmulation="yes"/><libinput>'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rc.xml"
            path.write_text(prefix + profile + '</libinput></openbox_config>', encoding="utf-8")
            parsed = touch.read_configuration(path)
            self.assertEqual(parsed["matrix"], [0, 1, 0, -1, 0, 1])
            self.assertEqual(parsed["map_to_output"], "SPI-1")
            path.write_text(prefix + profile * 2 + '</libinput></openbox_config>', encoding="utf-8")
            with self.assertRaises(touch.CalibrationError):
                touch.read_configuration(path)


class TouchCalibrationCollectorTests(unittest.TestCase):
    def collect_stationary_contacts(self, source):
        import pygame

        batches = []
        for point in touch.TARGETS:
            if source == "mouse":
                batches.extend([
                    [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point, touch=False)],
                    [pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=point, touch=False)],
                ])
            else:
                normalized = {"x": point[0] / touch.WIDTH, "y": point[1] / touch.HEIGHT,
                              "finger_id": 1, "touch_id": 1}
                # SDL duplicates must not turn one native contact into two.
                batches.extend([
                    [pygame.event.Event(pygame.FINGERDOWN, **normalized),
                     pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point, touch=True)],
                    [pygame.event.Event(pygame.FINGERUP, **normalized),
                     pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=point, touch=True)],
                ])
        moments = [0.0]

        def next_batch():
            self.assertTrue(batches, "Collector did not finish after five complete contacts")
            moments[0] += 0.5
            return batches.pop(0)

        with patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}), \
             patch.object(pygame.event, "get", side_effect=next_batch), \
             patch.object(pygame.time, "Clock"), \
             patch.object(touch.time, "monotonic", side_effect=lambda: moments[0]):
            contacts, actual_source = touch.collect_contacts(windowed=True)
        self.assertFalse(batches)
        self.assertEqual(actual_source, source)
        self.assertEqual(len(contacts), 5)
        for contact, target in zip(contacts, touch.TARGETS):
            self.assertEqual(contact["event_samples"], 1)
            self.assertEqual(contact["retained_samples"], 1)
            self.assertTrue(contact["quality_reasons"])
            self.assertAlmostEqual(contact["duration_seconds"], 0.5)
            for actual, expected in zip(contact["observed_pixels"], target):
                self.assertAlmostEqual(actual, expected)
        # Test quality rejection independently of the windowed-mode guard.
        report = touch.build_report(contacts, {"matrix": [1, 0, 0, 0, 1, 0]}, actual_source)
        self.assertEqual(report["status"], "invalid")
        self.assertNotIn("proposed_matrix", report)
        self.assertTrue(report["reasons"])
        self.assertFalse(report["applied"])

    def test_stationary_mouse_contacts_finish_without_motion_events(self):
        self.collect_stationary_contacts("mouse")

    def test_stationary_finger_contacts_ignore_synthetic_mouse_duplicates(self):
        self.collect_stationary_contacts("finger")


if __name__ == "__main__":
    unittest.main()
