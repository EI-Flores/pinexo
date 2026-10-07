import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from tests.support import PROJECT
import forecast_helpers as helpers
import manage

TZ = timezone(timedelta(hours=-6))
NOW = datetime(2026, 10, 6, 15, 30, tzinfo=TZ)


class ForecastTests(unittest.TestCase):
    def forecast(self, probabilities):
        return {"hourly": {"time": [f"2026-10-06T{hour:02}:00" for hour in range(15, 15 + len(probabilities))], "precipitation_probability": probabilities, "temperature_2m": [22] * len(probabilities)}}

    def test_past_rain_cannot_trigger_an_alert(self):
        self.assertIsNone(helpers.compute_rain_alert(self.forecast([100, 20, 10]), NOW))

    def test_precipitation_period_ends_at_its_timestamp_and_does_not_extend_past_horizon(self):
        alert = helpers.compute_rain_alert(self.forecast([100, 70, 20, 80, 20, 20, 20, 99]), NOW)
        self.assertEqual(alert["start"], NOW)
        self.assertEqual(alert["end"].hour, 18)
        self.assertEqual(alert["probability"], 80)
        self.assertEqual(len(alert["intervals"]), 2)

    def test_missing_or_invalid_probabilities_are_never_zero_rain(self):
        forecast = self.forecast([None, "80", -5, 120, float("nan")])
        self.assertIsNone(helpers.compute_rain_alert(forecast, NOW))
        self.assertTrue(all(row["probability"] is None for row in helpers.future_hourly(forecast, NOW)))

    def test_forecast_from_yesterday_has_no_future_alert(self):
        forecast = self.forecast([100, 100, 100])
        self.assertIsNone(helpers.compute_rain_alert(forecast, NOW + timedelta(days=1)))

    def test_daily_dates_use_the_local_day_and_missing_values_remain_unknown(self):
        forecast = {"daily": {"time": ["2026-10-06", "2026-10-07", "2026-10-08"]}}
        utc_now = datetime(2026, 10, 7, 1, tzinfo=timezone.utc).astimezone(TZ)
        rows = helpers.daily_rows(forecast, utc_now, include_today=False)
        self.assertEqual([row["date"].day for row in rows], [7, 8])
        self.assertIsNone(rows[0]["min"])
        self.assertIsNone(rows[0]["sunrise"])


class ServiceTests(unittest.TestCase):
    def test_dry_run_never_writes_or_runs_commands(self):
        with patch.object(manage, "_run", side_effect=AssertionError("must not run")), patch.object(manage, "atomic_write", side_effect=AssertionError("must not write")), contextlib.redirect_stdout(io.StringIO()) as result:
            self.assertEqual(manage.main(["--dry-run"]), 0)
        self.assertIn("--service", result.getvalue())

    def test_unit_argument_protects_systemd_percent_and_dollar_expansion(self):
        unit = manage.render_unit(PurePosixPath('/home/user/panel %x $HOME "a"'))
        self.assertIn("%%x", unit)
        self.assertIn("$$HOME", unit)
        self.assertIn('\\"a\\"', unit)
        self.assertIn("WantedBy=default.target", unit)

    def test_unrelated_service_is_not_overwritten_or_controlled(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "pi-clima.service"
            destination.write_text("[Service]\nExecStart=/other/program\n", encoding="utf-8")
            with patch.object(manage, "unit_path", return_value=destination), patch.object(manage, "_run", side_effect=AssertionError("must not run")):
                with self.assertRaises(RuntimeError):
                    manage.enable_service()
            self.assertIn("/other/program", destination.read_text())

    def test_external_unrelated_unit_is_not_shadowed(self):
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory) / "external.service"
            external.write_text("[Service]\nExecStart=/other/program\n", encoding="utf-8")
            destination = Path(directory) / "pi-clima.service"
            reply = subprocess.CompletedProcess([], 0, stdout=str(external), stderr="")
            with patch.object(manage, "unit_path", return_value=destination), patch.object(manage, "_run", return_value=reply):
                with self.assertRaises(RuntimeError):
                    manage.enable_service()
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
