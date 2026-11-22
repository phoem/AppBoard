"""Integration tests with the actual Qt Quick shell, Chromium and a loopback model double."""
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QEventLoop, QObject, QPointF, Qt, QTimer, Slot
from PySide6.QtTest import QTest
from PySide6.QtQml import QQmlContext, QQmlExpression, qmlContext
from PySide6.QtWidgets import QApplication, QMessageBox

from appboard.__main__ import desktop
from appboard.editor import Editor, PageRequest
from appboard.generation import Generator
from appboard.project import DrawingProject, PagedProject, Project


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
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.app, cls.board, cls.engine = desktop(Path(folder.name) / "library.sqlite3")
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
        app_id = session.version.app_id
        session.close()
        self.wait(lambda: not self.window.findChildren(QObject, "appPanel"))
        def pick_saved_app():
            dialog = QApplication.activeModalWidget()
            dialog.filter.setText("Arithmetic experiment")
            dialog.open_button.click()
        QTimer.singleShot(0, pick_saved_app)
        self.board.open()
        reopened, = self.board.sessions
        self.assertEqual(reopened.version.app_id, app_id)
        self.assertEqual(reopened.project.html, source)
        reopened.apply(Project("Colour", '<script>console.info("revised")</script>'))
        self.assertFalse(reopened.dirty)
        view = self.window.findChild(QObject, "guestView")
        console = Console(view)
        self.wait(lambda: "revised" in console.messages)
        self.assertEqual(self.board.library.load(app_id)[0].name, "Colour")

    def test_import_detaches_source_and_failed_autosave_can_be_retried(self):
        path = Path(self.temp.name) / "shared.appboard"
        Project("First").save(path)
        QTimer.singleShot(0, lambda: QApplication.activeModalWidget().import_button.click())
        with patch("appboard.host.QFileDialog.getOpenFileName", return_value=(str(path), "")):
            self.board.open()
        session, = self.board.sessions
        with patch.object(self.board.library, "store", side_effect=sqlite3.OperationalError("disk full")):
            session.apply(Project("My edit"))
        self.assertIn("disk full", session.storageStatus)
        Project("External edit").save(path)
        with patch("appboard.host.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            session.close()
        self.assertEqual(Project.load(path).name, "External edit")
        self.assertIn(session, self.board.sessions)
        self.assertTrue(session.dirty)
        self.assertTrue(session.save())
        self.assertEqual(self.board.library.load(session.version.app_id)[0].name, "My edit")

    def test_unfinished_generation_reopens_with_original_prompt_and_custom_draft(self):
        draft = DrawingProject("Draft", "function draw(g){g.clear('red')}")
        request = PageRequest("Make a transit diary", draft, "http://localhost/v1", "fixture")
        with patch.object(self.board, "draft", return_value=request), patch.object(Generator, "generate_page"):
            self.board.create()
        session, = self.board.sessions
        app_id = session.version.app_id
        self.assertTrue(self.board.library.load(app_id)[1])
        session.close()
        session = self.board.open_record(app_id)
        self.assertTrue(session.canRetry)
        self.assertFalse(session.canSave)
        session.pages.client.model = "fixture"
        with patch.object(Generator, "generate_page") as generate:
            session.retryPage()
            context = generate.call_args.args[0]
            self.assertEqual(context["currentPage"]["script"], draft.script)
            self.assertEqual(context["request"], request.prompt)
            session.pages.finish(DrawingProject("Diary", "function draw(g){g.text(1,1,'Trips')}"))
        self.assertEqual(self.board.library.load(app_id)[:2], (session.project, False))

    def test_failed_generation_preserves_editor_source(self):
        project = Project("My sketch", "<canvas></canvas>")
        editor = Editor(project)
        editor.endpoint.setText("file:///unsupported")
        editor.picker.combo.addItem("Unavailable", ("file:///unsupported", "invalid"))
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

    def test_native_window_draws_pixels_and_receives_input(self):
        script = """
        let color = '#ee2211', label = '';
        function draw(g,w,h) {
            g.clear('#ffffff'); g.rect(4,4,40,40,color); g.text(60,10,label,18,'black');
            g.path('M90 4 L130 4 L130 44 Z','blue');
        }
        function input(e) { if(e.type==='down') color='#119922'; if(e.type==='key') label=e.text; }
        """
        session = self.board.mount(DrawingProject("Paint", script))
        surface = self.window.findChild(QObject, "nativeSurface")
        self.assertIsNotNone(surface)
        self.assertIsNone(self.window.findChild(QObject, "guestView"))
        xy = surface.mapToScene(QPointF(20, 20)).toPoint()
        def pixel(at=xy):
            image = self.window.grabWindow()
            return image.pixelColor(round(at.x()*image.devicePixelRatio()), round(at.y()*image.devicePixelRatio())).name()
        self.wait(lambda: pixel() == "#ee2211")
        self.wait(lambda: pixel(surface.mapToScene(QPointF(120,12)).toPoint()) == "#0000ff")
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, xy)
        self.wait(lambda: pixel() == "#119922")
        QTest.keyClick(self.window, Qt.Key.Key_K)
        self.wait(lambda: session.surface.nodes[2]["value"].lower() == "k")
        self.assertFalse(session.surface.problem)
        session.apply(DrawingProject("Edited", "function draw(g){g.clear('blue')}"))
        self.wait(lambda: pixel() == "#0000ff")
        chosen = Path(self.temp.name) / "edited.v2"
        file = chosen.with_name("edited.v2.appboard")
        with patch("appboard.host.QFileDialog.getSaveFileName", return_value=(str(chosen), "")):
            self.assertTrue(session.exportApp())
        session.close()
        self.wait(lambda: not self.window.findChildren(QObject, "appPanel"))
        reopened = self.board.open_path(file)
        self.assertEqual(reopened.surface.nodes[0]["color"], "blue")

    @unittest.skipUnless(os.getenv("APPBOARD_LIVE_MODEL"), "set APPBOARD_LIVE_MODEL to run real inference")
    def test_live_progressive_feature(self):
        brief = ("Build a two-page pocket sketchbook. Main page title Sketchbook. Draw a visible Gallery "
                 "control with g.featureButton(16,56,160,40,'Gallery','gallery',"
                 "'Draw a gallery with a violet circle and a Gallery heading','teal'). "
                 "Generate only the main page first.")
        session = self.board.mount(PagedProject(brief=brief))
        flow = session.pages
        flow.client.model = os.environ["APPBOARD_LIVE_MODEL"]
        previews = []
        flow.client.preview.connect(lambda _: previews.append((session.building, len(session.surface.nodes))))
        flow.start("", brief)
        self.wait(lambda: not session.building, timeout=150)
        self.assertFalse(session.canRetry, session.pageStatus)
        self.assertTrue(any(busy and nodes for busy, nodes in previews))
        self.assertEqual(session.project.features, {})
        view = self.window.findChild(QObject, "nativeSurface")
        labels = [n for n in session.surface.nodes if n.get("kind") == "text" and "gallery" in n["value"].lower()]
        self.assertTrue(labels, session.project.script)
        label = labels[-1]
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         view.mapToScene(QPointF(label["x"]+3, label["y"]+3)).toPoint())
        self.wait(lambda: not session.building, timeout=150)
        self.assertEqual(flow.key, "gallery", session.pageStatus)
        self.assertFalse(session.surface.problem)
        self.assertTrue(session.surface.nodes)

    @unittest.skipUnless(os.getenv("APPBOARD_LIVE_MODEL"), "set APPBOARD_LIVE_MODEL to run real inference")
    def test_live_local_model(self):
        generated, errors = [], []
        generator = Generator(model=os.environ["APPBOARD_LIVE_MODEL"])
        generator.generated.connect(generated.append)
        generator.failed.connect(errors.append)
        generator.generate("Draw a tiny field tally app. Draw the integer alone with g.text, initially 0. "
                           "A pointer down anywhere increments the count. Use browser false.", DrawingProject())
        self.wait(lambda: generated or errors, timeout=130)
        self.assertEqual(errors, [])
        session = self.board.mount(generated[0])
        self.assertFalse(session.surface.problem, session.surface.problem)
        view = self.window.findChild(QObject, "nativeSurface")
        xy = view.mapToScene(QPointF(80, 60)).toPoint()
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, xy)
        self.wait(lambda: any(n.get("value") == "1" for n in session.surface.nodes))
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

    def test_picker_routes_generation_and_runs_native_browser_immediately(self):
        calls = []
        release_home = threading.Event()
        class Server(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, body, kind):
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except ConnectionError:
                    # Discovery requests can be cancelled when Studio closes.
                    return

            def do_GET(self):
                if self.path.endswith("/models"):
                    self.send(b'{"data":[{"id":"shared"},{"id":"shared"}]}', "application/json")
                else:
                    self.send(b"<title>Native toolbar test</title>", "text/html")

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append((self.path, data))
                home = json.loads(data["messages"][1]["content"])["page"] == "main"
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                def delta(chunk):
                    raw = json.dumps({"choices": [{"delta": {"content": chunk}}]}).encode()
                    self.wfile.write(b"data: " + raw + b"\n\n")
                    self.wfile.flush()
                first = "g.clear('#176840');g.text(5,5,'Library');"
                second = "g.text(5,30,'Open browser');"
                handler = ("if(e.type==='down'){g.data.visits=(g.data.visits||0)+1; "
                           "g.openFeature('browser','Browse reference websites');}")
                if not home:
                    first, second = "g.clear('white');", "g.text(5,5,'Open');"
                    handler = "if(e.type==='down')g.browser.navigate('" + base + "/page');"
                delta('{"name":"Library","browser":' + json.dumps(not home) +
                      ',"toolbarHeight":80,"sections":[' + json.dumps(first))
                if home:
                    release_home.wait(8)
                delta(',' + json.dumps(second) + '],"input":' + json.dumps(handler) + '}')
                self.wfile.write(b"data: [DONE]\n\n")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        a, b = base + "/lm/v1", base + "/ollama/v1"
        picker_items = []
        timer = QTimer(interval=20)
        deadline = time.monotonic() + 12

        def drive_editor():
            editor = QApplication.activeModalWidget()
            if not isinstance(editor, Editor):
                return
            if time.monotonic() > deadline:
                editor.done(0)
                return
            if editor.picker.clients or picker_items:
                return
            combo = editor.picker.combo
            picker_items.extend(combo.itemData(i) for i in range(combo.count()))
            if (b, "shared") in picker_items:
                combo.setCurrentIndex(picker_items.index((b, "shared")))
                editor.settings = Mock()  # Keep the user's saved provider preference.
                editor.prompt.setText("Create a browser with a native Open button")
                editor.generate.click()

        with patch("appboard.modelpicker.LOCAL_SERVERS", {a: "LM Studio", b: "Ollama"}), \
             patch.dict(os.environ, {"APPBOARD_MODEL_URL": a, "APPBOARD_MODEL": ""}):
            timer.timeout.connect(drive_editor)
            timer.start()
            try:
                self.board.create()
            finally:
                timer.stop()
        self.assertCountEqual(picker_items, [(a, "shared"), (b, "shared")])
        session = self.board.sessions[0]
        self.wait(lambda: any(n.get("value") == "Library" for n in session.surface.nodes))
        live_view = self.window.findChild(QObject, "nativeSurface")
        point = live_view.mapToScene(QPointF(200, 30)).toPoint()
        def first_paint():
            image = self.window.grabWindow()
            scale = image.devicePixelRatio()
            return image.pixelColor(round(point.x()*scale), round(point.y()*scale)).name() == "#176840"
        self.wait(first_paint)
        self.assertTrue(session.building)
        self.assertFalse(session.canSave)
        self.assertEqual(session.project.features, {})
        release_home.set()
        self.wait(lambda: not session.building)
        self.assertEqual(len(calls), 1)
        route, request = calls[0]
        self.assertEqual((route, request["model"]), ("/ollama/v1/chat/completions", "shared"))
        self.assertTrue(request["stream"])
        self.assertEqual(len(self.board.sessions), 1)
        session = self.board.sessions[0]
        self.assertTrue(session.native)
        surface = self.window.findChild(QObject, "nativeSurface")
        def click():
            QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             surface.mapToScene(QPointF(15,15)).toPoint())
        click()
        self.wait(lambda: session.pages.key == "browser")
        self.assertEqual(len(calls), 2)
        self.assertEqual(session.surface.data["visits"], 1)
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         surface.mapToScene(QPointF(15,15)).toPoint())
        self.wait(lambda: session.port.state.get("title") == "Native toolbar test")
        browser = self.window.findChild(QObject, "browserView")
        session.apply(DrawingProject("Restyled", "function draw(g){g.clear('red')}", True))
        self.assertIs(self.window.findChild(QObject, "browserView"), browser)
        self.assertEqual(session.port.state["title"], "Native toolbar test")
        session.back()
        click()
        self.assertEqual(session.pages.key, "browser")
        self.assertEqual(session.surface.data["visits"], 2)
        path = Path(self.temp.name) / "library.appboard"
        with patch("appboard.host.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            self.assertTrue(session.exportApp())
        saved_id = session.version.app_id
        session.close()
        self.wait(lambda: not self.board.sessions and not self.window.findChildren(QObject, "appPanel"))
        session = self.board.open_record(saved_id)
        surface = self.window.findChild(QObject, "nativeSurface")
        click()
        self.assertEqual(session.pages.key, "browser")
        self.assertEqual(session.active_page.name, "Restyled")
        self.assertEqual(len(calls), 2)
        self.assertEqual(Project.load(path), session.project)

    def test_invalid_native_generation_stays_editable(self):
        editor = Editor(DrawingProject())
        editor.settings = Mock()
        invalid = DrawingProject("Broken", "function draw(g){g.noSuchOperation();}")
        editor.generated(invalid)
        self.assertEqual(editor.result(), 0)
        self.assertEqual(editor.draft(), invalid)
        self.assertIn("TypeError", editor.status.text())

    def test_invalid_section_requests_one_early_repair_and_rejects_empty_page(self):
        session = self.board.mount(PagedProject(brief="Field notebook"))
        flow = session.pages
        flow.client.model = "fixture"
        with patch.object(flow.client, "generate_page") as generate:
            flow.start("", "Field notebook", draft=DrawingProject())
            self.assertEqual(set(generate.call_args.args[0]), {"request", "page", "viewport"})
            flow.preview("function draw(g){g.ctx.fillStyle='red'}")
            self.assertEqual(generate.call_count, 2)
            self.assertIn("fillStyle", generate.call_args.args[0]["correction"]["error"])
            flow.finish(DrawingProject("Empty", "function draw(){}"))
            self.assertTrue(session.canRetry)
            self.assertIn("no native graphics", session.pageStatus)
            self.assertEqual(session.project.name, "Untitled app")

    def test_click_failure_is_repaired_before_saving_a_feature(self):
        session = self.board.mount(PagedProject("Notebook", brief="Generate only the main page"))
        flow = session.pages
        flow.client.model = "fixture"
        with patch.object(flow.client, "generate_page") as generate:
            flow.open("gallery", "Show a gallery of images")
            ctx = generate.call_args.args[0]
            self.assertEqual(ctx["request"], "Show a gallery of images")
            self.assertNotIn(session.project.script, json.dumps(ctx))
            self.assertNotIn(session.project.brief, json.dumps(ctx))
            flow.finish(DrawingProject("Gallery", "function draw(g){g.text(8,8,'More')} "
                                       "function input(e,g){if(e.type==='down' && e.x>8)g.missing()}"))
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(self.board.library.load(session.version.app_id)[0].features, {})
            flow.finish(DrawingProject("Gallery", "function draw(g){g.text(8,8,'Images')} "
                                       "function input(e,g){g.data.clicked=true;g.openFeature('more','More images')}"))
        self.assertEqual(flow.key, "gallery")
        self.assertNotIn("clicked", session.surface.data)
        self.assertFalse(session.building)
        self.assertIn("gallery", self.board.library.load(session.version.app_id)[0].features)

    def test_cancel_failed_feature_and_retry_preserve_committed_page(self):
        path = Path(self.temp.name) / "existing.appboard"
        original = DrawingProject("Home", "function draw(g){g.clear('green')}")
        original.save(path)
        session = self.board.open_path(path)
        flow = session.pages
        flow.client.model = "fixture"
        with patch.object(flow.client, "generate_page") as generate:
            flow.open("history", "Show the history")
            flow.preview("function draw(g){g.clear('blue')}")
            self.assertEqual(session.surface.nodes[0]["color"], "blue")
            session.cancelPage()
            flow.finish(DrawingProject("Late result"))
            self.assertEqual(session.surface.nodes[0]["color"], "green")
            self.assertFalse(session.dirty)
            session.retryPage()
            flow.client.failed.emit("Offline")
            self.assertTrue(session.canRetry)
            self.assertEqual(session.project, original)
            session.retryPage()
            flow.finish(DrawingProject("History", "function draw(g){g.clear('purple')}"))
            self.assertEqual(generate.call_count, 3)
        self.assertEqual(flow.key, "history")
        self.assertEqual(session.project.version, 3)
        self.assertEqual(Project.load(path).version, 2)
        session.back()
        self.assertEqual(session.surface.nodes[0]["color"], "green")
