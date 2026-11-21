"""Per-instance navigation and generation for progressive native apps."""
import os
from dataclasses import asdict, replace

import quickjs
from PySide6.QtCore import QObject, QSettings

from .generation import Generator
from .native import Drawing
from .project import PagedProject, Project

DRAW_ERRORS = (ValueError, quickjs.JSException, OverflowError, RecursionError)


class Pages(QObject):
    def __init__(self, session):
        super().__init__(session)
        self.session = session
        self.surface = session.surface
        self.client = Generator(self)
        settings = QSettings()
        self.client.base = os.getenv("APPBOARD_MODEL_URL") or settings.value("generation/endpoint", self.client.base)
        self.client.model = os.getenv("APPBOARD_MODEL") or settings.value("generation/model", "")
        self.client.preview.connect(self.preview)
        self.client.generated.connect(self.finish)
        self.client.failed.connect(self.fail)
        self.surface.featureRequested.connect(self.open)
        self.key = ""
        self.history = []
        self.job = None
        self.retry_job = None
        self.previous = None
        self.message = ""
        self.home_ready = True
        self.context = None

    @property
    def root(self):
        saved = self.session.project
        if isinstance(saved, PagedProject):
            return saved
        return PagedProject(saved.name, saved.script, saved.browser, saved.toolbarHeight)

    @property
    def page(self):
        return self.root.page(self.key)

    def update(self):
        self.session.changed.emit()

    def open(self, key, brief):
        if self.job or key == self.key:
            return
        if key in self.root.features:
            for index, (prior_key, _) in enumerate(self.history):
                if prior_key == key:
                    self.history = self.history[:index + 1]
                    self.back()
                    return
            self.history.append((self.key, self.surface.drawing))
            self.key = key
            self.retry_job, self.message = None, ""
            self.update()
            self.surface.load(self.page.script)
        elif len(self.root.features) >= 64:
            self.message = "This app already contains 64 feature pages."
            self.update()
        else:
            self.start(key, brief)

    def start(self, key, request, revision=False, draft=None):
        if self.job:
            return
        if not self.client.model:
            provider = self.session.board.choose_provider()
            if not provider:
                self.retry_job = (key, request, revision, draft)
                self.message = "Choose a model to draw this page."
                self.update()
                return
            self.client.base, self.client.model = provider
        self.job = (key, request, revision, draft)
        self.retry_job = None
        self.previous = self.surface.drawing
        self.surface.stop()
        self.message = "Drawing main page…" if not key else f"Drawing {key}…"
        root = self.root
        context = {"app": root.brief, "page": key or "main", "request": request,
                   "viewport": list(self.surface.size), "existingFeatures": list(root.features)}
        if key:
            context["mainPageSource"] = root.script
        if revision or key or draft:
            context["currentPage"] = asdict(draft or self.page)
        # Runtime values stay local. The model can reuse the shape of shared state.
        context["sharedDataKeys"] = list(self.surface.data)
        self.context = context
        self.update()
        self.client.generate_page(context)

    def preview(self, script):
        if not self.job:
            return
        try:
            frame = Drawing(script).frame(*self.surface.size, browser=self.session.port.state, data=self.surface.data)
        except DRAW_ERRORS:
            return  # Keep the last valid preview. The complete page is checked before installation.
        self.surface.nodes = frame["nodes"]
        self.surface.frameChanged.emit()

    def install(self, key, page):
        root = self.root
        if not root.brief and self.job:
            root = replace(root, brief=self.job[1] if not key else root.name)
        if key:
            root = replace(root, features={**root.features, key: asdict(page)})
        else:
            root = replace(root, name=page.name, script=page.script, browser=page.browser, toolbarHeight=page.toolbarHeight)
        Project.parse(asdict(root))
        self.session.project = root

    def finish(self, page):
        if not self.job:
            return
        key, _, revision, _ = self.job
        try:
            Drawing(page.script).frame(*self.surface.size, browser=self.session.port.state, data=self.surface.data)
            self.install(key, page)
        except DRAW_ERRORS as exc:
            if "correction" not in self.context:
                self.context = {**self.context, "correction": {"error": str(exc)[:1000], "source": page.script}}
                self.message = "Correcting the generated drawing…"
                self.update()
                self.client.generate_page(self.context)
                return
            self.fail(str(exc))
            return
        if key != self.key and not revision:
            self.history.append((self.key, self.previous))
        self.key, self.job, self.previous = key, None, None
        self.context = None
        self.home_ready = True
        self.message = ""
        self.update()
        self.surface.load(page.script)

    def restore(self):
        self.surface.drawing, self.previous = self.previous, None
        self.job = None
        self.context = None
        self.surface.redraw()

    def fail(self, message):
        if self.job:
            self.retry_job = self.job
            self.restore()
        self.message = message
        self.update()

    def cancel(self):
        self.client.cancel()
        if self.job:
            self.retry_job = self.job
            self.restore()
        self.message = "Generation stopped." if self.retry_job else ""
        self.update()

    def back(self):
        if self.job:
            self.cancel()
            return
        if self.history:
            self.surface.stop()
            self.key, self.surface.drawing = self.history.pop()
            self.retry_job, self.message = None, ""
            self.update()
            if self.surface.drawing:
                self.surface.redraw()
            else:
                self.surface.load(self.page.script)

    def retry(self):
        if self.retry_job:
            self.start(*self.retry_job)
