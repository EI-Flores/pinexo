"""Single satellite-detail downloader with one replaceable pending request."""
from __future__ import annotations

import logging
from pathlib import Path
import queue
import threading

from satellite_detail import fetch_detail

LOG = logging.getLogger(__name__)


class DetailWorker:
    """Keep at most one in-flight request and the latest pending request."""

    def __init__(self, directory, events, stop):
        self.directory = Path(directory)
        self.events = events
        self.stop = stop
        self._pending = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._thread = None

    def start(self):
        """Start once; repeated calls never create additional downloaders."""
        with self._lock:
            if self._thread is not None or self.stop.is_set():
                return
            self._thread = threading.Thread(target=self._run, name="satellite-detail", daemon=True)
            self._thread.start()

    def request(self, request):
        """Replace pending work, retaining the in-flight request's own token."""
        if not isinstance(request, dict):
            raise ValueError("Solicitud de detalle inválida")
        item = dict(request)
        if isinstance(item.get("extent"), (tuple, list)):
            item["extent"] = list(item["extent"])
        with self._lock:
            if self.stop.is_set():
                return False
            try:
                self._pending.get_nowait()
            except queue.Empty:
                pass
            else:
                self._pending.task_done()
            self._pending.put_nowait(item)
        return True

    def _run(self):
        while not self.stop.is_set():
            try:
                request = self._pending.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if self.stop.is_set():
                    break
                try:
                    event = fetch_detail(request, self.directory, self.stop)
                except Exception as exc:
                    if self.stop.is_set():
                        break
                    LOG.warning("No se descargó el detalle satelital: %s", exc)
                    message = " ".join(str(exc).split())[:160] or "No se pudo cargar el detalle"
                    event = {"kind": "satellite_detail", "request_token": request.get("request_token"),
                             "error": message}
                if not self.stop.is_set():
                    self.events.put(event)
            finally:
                self._pending.task_done()
