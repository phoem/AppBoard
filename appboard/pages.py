"""Per-instance navigation and generation for progressive native apps."""
import os
from dataclasses import asdict, replace

import quickjs
from PySide6.QtCore import QObject, QSettings

from .generation import Generator
from .native import Drawing
from .project import DrawingProject, PagedProject, Project

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
        self.client.partialPreview.connect(lambda script: self.preview(script, provisional=True))
        self.client.pageTitle.connect(self.show_title)
        self.client.generated.connect(self.finish)
        self.client.failed.connect(self.fail)
        self.surface.featureRequested.connect(self.open)
        self.key = ""
        self.history = []
        self.job = None
        self.retry_job = None
        self.previous = None
        self.message = ""
        self.last_correction = ""
        self.home_ready = True
        self.preview_heading = ""
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
        self.last_correction = ""
        self.retry_job = None
        self.previous = self.surface.drawing
        self.surface.stop()
        if not revision:
            heading = key.replace("_", " ").replace("-", " ").capitalize() if key else request
            self.preview_heading = " ".join(heading.split())[:140]
        self.message = f"Waiting for {self.client.model}…"
        root = self.root
        context = {"page": key or "main", "request": request, "viewport": list(self.surface.size)}
        if key:
            context["pageKind"] = "feature"
        if root.brief and root.brief != request and (revision or not key):
            context["app"] = root.brief
        if root.features:
            context["existingFeatures"] = list(root.features)
        if revision or (draft and draft != DrawingProject()):
            context["currentPage"] = asdict(draft or self.page)
        elif key:
            context["fromPage"] = self.page.name
            context["task"] = ("Implement the requested feature here. Draw its contents or its empty state "
                               "on this page; a link to another page is insufficient.")
            context["appName"] = root.name
            context["palette"] = list(dict.fromkeys(n["color"] for n in self.surface.nodes if "color" in n))[:8]
        # Runtime values stay local. The model can reuse the shape of shared state.
        if self.surface.data or key:
            context["sharedDataKeys"] = list(self.surface.data)
        if key and self.surface.data:
            context["collectionKeys"] = [name for name, value in self.surface.data.items() if isinstance(value, list)]
        self.context = context
        self.update()
        self.client.generate_page(context)

    def show_title(self, name):
        if self.job:
            self.message = f"Drawing {name}…"
            if self.preview_heading:
                self.preview_heading = name
            self.update()

    def preview(self, script, provisional=False):
        if not self.job:
            return
        try:
            frame = Drawing(script).frame(*self.surface.size, browser=self.session.port.state, data=self.surface.data)
        except DRAW_ERRORS as exc:
            if provisional or (self.job[0] and isinstance(exc, quickjs.JSException) and
                               str(exc).startswith(("SyntaxError:", "ReferenceError:"))):
                # A feature prefix may end inside a loop or before a helper declaration.
                return
            self.correct(script, exc, "drawing section")
            return
        if not frame["nodes"]:
            return
        if self.preview_heading:
            # Retain the heading until the model has drawn more than a flat background.
            first = frame["nodes"][0]
            background_only = (len(frame["nodes"]) == 1 and first["kind"] == "rect" and
                               (first["x"], first["y"], first["w"], first["h"]) == (0, 0, *self.surface.size))
            if not background_only:
                self.preview_heading = ""
                self.update()
        self.surface.nodes = frame["nodes"]
        self.surface.frameChanged.emit()

    def correct(self, source, exc, stage):
        if "correction" in self.context:
            self.client.cancel()
            self.fail(str(exc))
            return
        reason = str(exc).partition("\n")[0][:240]
        self.last_correction = f"Last correction ({self.job[0] or 'main'}, {stage}): {reason}"
        self.context = {**self.context, "correction": {"error": str(exc)[:1000], "source": source}}
        self.message = "Correcting the generated drawing…"
        self.update()
        self.client.generate_page(self.context)

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

    def validate_page(self, page):
        drawing = Drawing(page.script)
        width, height = self.surface.size
        if page.browser:
            height = min(height, page.toolbarHeight)
        state = self.session.port.state
        frame = drawing.frame(width, height, browser=state, data=self.surface.data)
        if not frame["nodes"] and not page.browser:
            raise ValueError("The page drew no native graphics. Draw visible content with g.text or g.rect.")
        # Exercise a few label positions in the disposable VM. Commands, navigation
        # and state from these synthetic clicks never reach the real app.
        points = [(n["x"] + 2, n["y"] + 2) for n in frame["nodes"] if n["kind"] == "text"]
        points = [(x, y) for x, y in points if 0 <= x < width and 0 <= y < height]
        for x, y in (points[:4] or [(width / 2, height / 2)]):
            for kind, buttons in (("down", 1), ("up", 0)):
                event = {"type": kind, "button": 0, "buttons": buttons, "x": x, "y": y}
                frame = drawing.frame(width, height, event, state, frame["data"])

    def finish(self, page):
        if not self.job:
            return
        key, _, revision, _ = self.job
        try:
            self.validate_page(page)
            self.install(key, page)
        except DRAW_ERRORS as exc:
            self.correct(page.script, exc, "completed page")
            return
        if key != self.key and not revision:
            self.history.append((self.key, self.previous))
        self.key, self.job, self.previous = key, None, None
        self.preview_heading = ""
        self.context = None
        self.home_ready = True
        self.message = ""
        self.session.save()
        self.update()
        self.surface.load(page.script)

    def restore(self):
        self.preview_heading = ""
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
