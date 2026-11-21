"""Integration tests with the actual Qt Quick shell, Chromium and a loopback model double."""
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QObject, QTimer, Slot
from PySide6.QtQml import QQmlContext, QQmlExpression, qmlContext
from PySide6.QtWidgets import QMessageBox

from appboard.__main__ import desktop
from appboard.editor import Editor
from appboard.generation import Generator
from appboard.project import Project


class Console(QObject):
    def __init__(self, view):
        super().__init__(view)
        self.messages = []
        self.context = QQmlContext(qmlContext(view), self)
        self.context.setContextProperty("recorder", self)
        self.subscription = QQmlExpression(self.context, view,
            "javaScriptConsoleMessage.connect(function(level, message) { recorder.record(message) })")
        self.subscription.evaluate()
        if self.subscription.hasError():
            raise RuntimeError(self.subscription.error().toString())

    @Slot(str)
    def record(self, message):
        self.messages.append(message)


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.board, cls.engine = desktop()
        cls.window = cls.engine.rootObjects()[0]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def tearDown(self):
        for session in self.board.sessions[:]:
            session.saved = session.project
            session.close()
        self.wait(lambda: not self.window.findChildren(QObject, "appPanel"))

    def wait(self, predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            loop = QEventLoop()
            QTimer.singleShot(20, loop.quit)
            loop.exec()
            if predicate():
                return
        self.fail("Timed out waiting for " + str(predicate))

    def expression(self, obj, code):
        expr = QQmlExpression(qmlContext(obj), obj, code)
        result, _ = expr.evaluate()
        self.assertFalse(expr.hasError(), expr.error().toString())
        return result

    def test_blank_window(self):
        self.assertEqual((self.window.width(), self.window.height()), (1920, 1080))
        self.assertFalse(self.board.sessions)
        self.assertFalse(self.window.findChildren(QObject, "appPanel"))

    def test_edit_run_save_close_reopen(self):
        source = '<button onclick="this.textContent=6*7">Multiply</button><script>document.querySelector("button").click();console.info("computed",document.querySelector("button").textContent)</script>'
        editor = Editor(Project())
        editor.name.setText("Arithmetic experiment")
        editor.source.setPlainText(source)
        editor.apply()
        session = self.board.mount(editor.result_project)
        view = self.window.findChild(QObject, "guestView")
        console = Console(view)
        self.wait(lambda: "computed 42" in console.messages)
        with tempfile.TemporaryDirectory(dir=self.temp.name) as folder:
            file = Path(folder) / "saved.appboard"
            with patch("appboard.host.QFileDialog.getSaveFileName", return_value=(str(file), "")):
                self.assertTrue(session.save())
            session.close()
            self.wait(lambda: not self.window.findChildren(QObject, "appPanel"))
            reopened = self.board.open_path(file)
            self.assertEqual(reopened.project.html, source)
            self.assertFalse(reopened.dirty)
            reopened.apply(Project("Colour", '<script>console.info("revised")</script>'))
            self.assertTrue(reopened.dirty)
            view = self.window.findChild(QObject, "guestView")
            console = Console(view)
            self.wait(lambda: "revised" in console.messages)
            self.assertTrue(reopened.save())
            self.assertEqual(Project.load(file).name, "Colour")

    def test_cancel_close_and_preserve_external_edits(self):
        path = Path(self.temp.name) / "shared.appboard"
        Project("First").save(path)
        session = self.board.open_path(path)
        session.apply(Project("My edit"))
        Project("External edit").save(path)
        with patch("appboard.host.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(session.save())
            session.close()
        self.assertEqual(Project.load(path).name, "External edit")
        self.assertIn(session, self.board.sessions)
        self.assertTrue(session.dirty)

    def test_failed_generation_preserves_editor_source(self):
        project = Project("My sketch", "<canvas></canvas>")
        editor = Editor(project)
        editor.endpoint.setText("file:///unsupported")
        editor.prompt.setText("Add a grid")
        editor.start()
        self.assertEqual(editor.draft(), project)
        self.assertTrue(editor.generate.isEnabled())
        self.assertIn("endpoint", editor.status.text())

    def test_independent_apps_and_opaque_origin(self):
        a = self.board.mount(Project("Drawing", '<canvas></canvas><script>const c=document.querySelector("canvas").getContext("2d"); c.fillRect(0,0,5,5);console.info("pixel",c.getImageData(0,0,1,1).data[3])</script>'))
        b = self.board.mount(Project("Second", '<script>try{parent.document}catch(e){console.info("opaque",e.name)};console.info("bridge",typeof qt)</script>'))
        consoles = [Console(view) for view in self.window.findChildren(QObject, "guestView")]
        self.assertFalse(b.hasBrowser)
        self.assertTrue(a.guestProfile.isOffTheRecord())
        self.wait(lambda: {"pixel 255", "opaque SecurityError", "bridge undefined"} <=
                  {msg for console in consoles for msg in console.messages})
        a.saved = a.project
        a.close()
        self.wait(lambda: len(self.window.findChildren(QObject, "appPanel")) == 1)
        self.assertEqual(self.board.sessions, [b])

    @unittest.skipUnless(os.getenv("APPBOARD_LIVE_MODEL"), "set APPBOARD_LIVE_MODEL to run real inference")
    def test_live_local_model(self):
        generated, errors = [], []
        generator = Generator(model=os.environ["APPBOARD_LIVE_MODEL"])
        generator.generated.connect(generated.append)
        generator.failed.connect(errors.append)
        generator.generate("Build a tiny field tally app. Give it a button with id add and a text output "
                           "with id count initially showing 0. Clicking add increments the displayed integer. "
                           "Keep the implementation under 30 lines. Use browser false.", Project())
        self.wait(lambda: generated or errors, timeout=130)
        self.assertEqual(errors, [])
        session = self.board.mount(generated[0])
        view = self.window.findChild(QObject, "guestView")
        console = Console(view)
        # Exercise the generated control inside the actual guest frame.
        probe = """if (mainFrame.children.length) mainFrame.children[0].runJavaScript(
            "if (document.querySelector('#add') && !window.probed) { window.probed=true; " +
            "document.querySelector('#add').click(); console.info('tally', document.querySelector('#count').textContent.trim()) }",
            0, function() {})"""
        def tallied():
            self.expression(view, probe)
            return "tally 1" in console.messages
        self.wait(tallied)
        path = Path(self.temp.name) / "live.appboard"
        session.project.save(path)
        self.assertEqual(Project.load(path), generated[0])

    def test_generation_and_live_browser(self):
        visits = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, data, kind):
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                visits.append(self.path)
                if self.path.endswith("/models"):
                    self.respond(b'{"data":[{"id":"fixture-model"}]}', "application/json")
                else:
                    self.respond(b"<title>Field notes</title><input value='retained'>", "text/html")

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                visits.append(payload["model"])
                toolbar = '<script>AppBoard.browser.navigate("' + base + '/notes")</script>'
                project = Project("Browser experiment", toolbar, True)
                data = {"choices": [{"message": {"content": project.encode().decode()}}]}
                self.respond(json.dumps(data).encode(), "application/json")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        base = f"http://127.0.0.1:{server.server_port}"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        generated, errors = [], []
        generator = Generator(base=base + "/v1", model="")
        generator.generated.connect(generated.append)
        generator.failed.connect(errors.append)
        generator.generate("Create a field notes browser", Project())
        self.wait(lambda: generated or errors)
        self.assertEqual(errors, [])
        self.assertIn("fixture-model", visits)
        session = self.board.mount(generated[0])
        self.wait(lambda: session.port.state.get("title") == "Field notes")
        browser = self.window.findChild(QObject, "browserView")
        self.expression(browser, '''runJavaScript("document.querySelector('input').value='still here'")''')
        session.apply(Project("Restyled", "<style>body{background:teal}</style>", True, 96))
        self.assertIs(self.window.findChild(QObject, "browserView"), browser)
        self.expression(browser, '''runJavaScript("document.title=document.querySelector('input').value")''')
        self.wait(lambda: session.port.state.get("title") == "still here")
        self.assertEqual(visits.count("/notes"), 1)
