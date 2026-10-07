"""Offline synchronization checks for the satellite detail worker."""
from pathlib import Path
import queue
import sys
import threading
import tempfile
import unittest
from unittest.mock import patch

from tests.support import PROJECT
import detail_worker


def request(token):
    return {"request_token": token, "extent": [-100, 18, -95, 21.5]}


def result(token):
    return {"kind": "satellite_detail", "request_token": token, "frames": []}


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.temporary = tempfile.TemporaryDirectory(prefix="detail-worker-")
        self.worker = detail_worker.DetailWorker(self.temporary.name, self.events, self.stop)

    def tearDown(self):
        self.stop.set()
        if self.worker._thread is not None:
            self.worker._thread.join(timeout=2)
            self.assertFalse(self.worker._thread.is_alive())
        self.temporary.cleanup()

    def test_start_is_idempotent_and_pending_is_latest(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def fetch(item, directory, stop):
            calls.append(item["request_token"])
            if len(calls) == 1:
                entered.set()
                self.assertTrue(release.wait(2))
            return result(item["request_token"])
        with patch.object(detail_worker, "fetch_detail", fetch):
            self.worker.start()
            first_thread = self.worker._thread
            self.worker.start()
            self.assertIs(self.worker._thread, first_thread)
            self.worker.request(request(1))
            self.assertTrue(entered.wait(2))
            self.worker.request(request(2))
            self.worker.request(request(3))
            self.worker.request(request(4))
            self.assertEqual(self.worker._pending.qsize(), 1)
            release.set()
            self.assertEqual(self.events.get(timeout=2)["request_token"], 1)
            self.assertEqual(self.events.get(timeout=2)["request_token"], 4)
            self.assertEqual(calls, [1, 4])
            self.stop.set()
            first_thread.join(timeout=2)

    def test_error_preserves_token_and_worker_can_continue(self):
        def fetch(item, directory, stop):
            if item["request_token"] == 1:
                raise ValueError("detalle de prueba\n" + "x" * 300)
            return result(item["request_token"])
        with patch.object(detail_worker, "fetch_detail", fetch):
            self.worker.start()
            self.worker.request(request(1))
            error = self.events.get(timeout=2)
            self.assertEqual(error["kind"], "satellite_detail")
            self.assertEqual(error["request_token"], 1)
            self.assertTrue(error["error"].startswith("detalle de prueba "))
            self.assertLessEqual(len(error["error"]), 160)
            self.worker.request(request(2))
            self.assertEqual(self.events.get(timeout=2), result(2))
            self.stop.set()
            self.worker._thread.join(timeout=2)

    def test_stop_suppresses_late_result_and_pending_work(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def fetch(item, directory, stop):
            calls.append(item["request_token"])
            entered.set()
            self.assertTrue(release.wait(2))
            return result(item["request_token"])
        with patch.object(detail_worker, "fetch_detail", fetch):
            self.worker.start()
            self.worker.request(request(1))
            self.assertTrue(entered.wait(2))
            self.worker.request(request(2))
            self.stop.set()
            self.assertFalse(self.worker.request(request(3)))
            release.set()
            self.worker._thread.join(timeout=2)
            self.assertEqual(calls, [1])
            self.assertTrue(self.events.empty())

    def test_stopped_worker_neither_starts_nor_accepts_requests(self):
        self.stop.set()
        self.worker.start()
        self.assertIsNone(self.worker._thread)
        self.assertFalse(self.worker.request(request(1)))
        self.assertTrue(self.worker._pending.empty())

    def test_pre_start_request_is_copied_and_latest(self):
        item = request(1)
        self.worker.request(item)
        item["request_token"] = 99
        item["extent"][0] = -999
        copied = self.worker._pending.get_nowait()
        self.worker._pending.task_done()
        self.assertEqual(copied["request_token"], 1)
        self.assertEqual(copied["extent"][0], -100)
        self.worker.request(request(2))
        self.worker.request(request(3))
        with patch.object(detail_worker, "fetch_detail", lambda item, *_: result(item["request_token"])):
            self.worker.start()
            self.assertEqual(self.events.get(timeout=2), result(3))
            self.stop.set()
            self.worker._thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
