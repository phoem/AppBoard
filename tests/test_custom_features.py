"""Opt-in desktop benchmark. Set APPBOARD_BENCH_MODEL to a local model identifier."""
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QEventLoop, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from appboard.__main__ import desktop
from appboard.project import PagedProject


class ReferencePages(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        titles = {"/index": "Reference index", "/detail": "Sample detail"}
        if self.path not in titles:
            self.send_error(404)
            return
        page = (f"<title>{titles[self.path]}</title>"
                "<a style='display:block;height:100vh' href='/detail'>Open sample</a>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)


@unittest.skipUnless(os.getenv("APPBOARD_BENCH_MODEL"), "set APPBOARD_BENCH_MODEL for live desktop benchmarks")
class CustomFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.app, cls.board, cls.engine = desktop(Path(folder.name) / "benchmark.sqlite3")
        cls.window = cls.engine.rootObjects()[0]
        cls.addClassCleanup(cls.window.close)

    def setUp(self):
        self.session = self.board.mount(PagedProject("Field station"))
        self.session.pages.client.model = os.environ["APPBOARD_BENCH_MODEL"]
        self.metrics = {}
        self.addCleanup(self.report)
        self.app.processEvents()

    def report(self):
        print(self.id(), json.dumps(self.metrics), flush=True)
        self.session.close()
        self.wait_for(lambda: not self.window.findChildren(QObject, "appPanel"))

    def wait_for(self, condition, timeout=5):
        deadline = time.perf_counter() + timeout
        while not condition():
            self.assertLess(time.perf_counter(), deadline, self.metrics)
            loop = QEventLoop()
            QTimer.singleShot(10, loop.quit)
            loop.exec()

    def elapsed(self):
        return round(time.perf_counter() - self.start, 3)

    def generate(self, key, brief):
        flow = self.session.pages
        original_request = flow.client._request
        provider_defaults = os.getenv("APPBOARD_BENCH_PROVIDER_DEFAULT") == "1"
        self.metrics["inference"] = "provider default" if provider_defaults else "AppBoard"
        def request(route, body, *args, **kwargs):
            if provider_defaults and route == "chat/completions":
                body = {k: v for k, v in body.items() if k != "reasoning_effort"}
            return original_request(route, body, *args, **kwargs)

        self.start = time.perf_counter()
        def frame_drawn():
            if not flow.preview_heading and any(n["kind"] != "rect" or
                    (n["x"], n["y"], n["w"], n["h"]) != (0, 0, *self.session.surface.size)
                    for n in self.session.surface.nodes):
                self.metrics.setdefault("first_frame_s", self.elapsed())
        self.window.frameSwapped.connect(frame_drawn, Qt.ConnectionType.QueuedConnection)
        try:
            with patch.object(flow.client, "_request", wraps=request) as requests:
                flow.open(key, brief)
                self.wait_for(lambda: not self.session.building, 250)
                self.metrics["ready_s"] = self.elapsed() if flow.key == key else None
                self.metrics["model_requests"] = sum(c.args[0] == "chat/completions" for c in requests.call_args_list)
                if self.session.lastCorrection:
                    self.metrics["correction"] = self.session.lastCorrection
                self.assertEqual(flow.key, key, self.session.pageStatus)
                self.wait_for(lambda: "first_frame_s" in self.metrics)
        finally:
            self.window.frameSwapped.disconnect(frame_drawn)
        self.surface = self.window.findChild(QObject, "nativeSurface")

    def click(self, item, x, y):
        local = QPointF(x, y)
        self.assertTrue(item.contains(local), f"Control at ({x}, {y}) is outside the visible surface")
        point = item.mapToScene(local).toPoint()
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)

    def labels(self):
        return [n for n in self.session.surface.nodes if n["kind"] == "text"]

    def click_label(self, *values):
        for value in values:
            for label in self.labels():
                if label["value"].strip(" <>←→◀▶").casefold() != value.casefold():
                    continue
                self.click(self.surface, label["x"] + 3, label["y"] + label["size"] / 2)
                return
        self.fail(f"Missing {values!r} in {[n['value'] for n in self.labels()]}")

    def test_reference_browser(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ReferencePages)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.generate("reference", "Make a web browser for looking up field references. Give it a clickable "
                      "address bar with placeholder 'Address' that starts empty. I can type any URL and press "
                      "Enter to visit it. Include buttons labeled Back and Forward for page history.")
        browser = self.window.findChild(QQuickItem, "browserView")
        self.assertIsNotNone(browser, "The feature did not open the Chromium surface")
        self.click_label("Address", "URL", "Enter a URL...", "")
        url = f"http://127.0.0.1:{server.server_port}/index"
        for char in url:
            event = QKeyEvent(QEvent.Type.KeyPress, ord(char.upper()), Qt.KeyboardModifier.NoModifier, char)
            self.app.sendEvent(self.window, event)
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        def loaded(title):
            return self.session.port.state.get("title") == title and not self.session.port.state["loading"]
        self.wait_for(lambda: loaded("Reference index"))
        self.metrics["first_site_loaded_s"] = self.elapsed()
        self.click(browser, 30, 30)
        self.wait_for(lambda: loaded("Sample detail"))
        self.click_label("Back")
        self.wait_for(lambda: loaded("Reference index"))
        self.click_label("Forward")
        self.wait_for(lambda: loaded("Sample detail"))
        self.metrics["history_verified"] = True
        self.assertEqual(self.metrics["model_requests"], 1, self.metrics)

    def test_core_sample_log(self):
        self.generate("strata", "Make a rock core logging tool. Draw buttons labeled Clay, Sand and Undo. "
                      "Each material click appends a layer; duplicates matter. Show the sequence in order "
                      "as one line joined by ' / '. Undo removes only the last layer.")
        for label in ("Clay", "Sand", "Clay"):
            self.click_label(label)
        self.assertTrue(any("clay / sand / clay" in n["value"].casefold() for n in self.labels()), self.labels())
        self.click_label("Undo")
        self.assertTrue(any(n["value"].casefold().endswith("clay / sand") for n in self.labels()), self.labels())
        self.metrics["sequence_and_undo_verified"] = True
        self.assertEqual(self.metrics["model_requests"], 1, self.metrics)
