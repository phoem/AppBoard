import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, Property, QSettings, QStandardPaths, Signal, Slot
from PySide6.QtQml import QQmlEngine

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLineEdit, QMessageBox

from .editor import Editor, PageRequest
from .library import Library
from .library_dialog import LibraryDialog
from .modelpicker import ModelPicker
from .native import DrawingSurface
from .pages import Pages
from .project import DrawingProject, PagedProject, Project
from .runtime import document, navigation_url, profile


class BrowserPort(QObject):
    stateChanged = Signal("QVariantMap")
    command = Signal(str, str)

    def __init__(self, session):
        super().__init__(session)
        self.session = session
        self.state = {}

    @Slot(str, str)
    def request(self, action, value):
        if not self.session.hasBrowser:
            return
        if action == "state":
            self.stateChanged.emit(self.state)
        elif action in {"back", "forward", "reload"}:
            self.command.emit(action, "")
        elif action == "navigate" and (url := navigation_url(value)):
            self.command.emit(action, url)


class Session(QObject):
    changed = Signal()
    reloadSource = Signal()
    removed = Signal()
    activated = Signal()
    browserCommand = Signal(str, str)

    def __init__(self, board, project, version=None, pending=False):
        super().__init__(board)
        self.board, self.project, self.version = board, project, version
        self.saved = project if version else None
        self.saved_pending = pending
        self.storage_message = ""
        self._html = document(project) if project.version == 1 else ""
        self._guest = None
        self._web = None
        self.port = BrowserPort(self)
        self.port.command.connect(self.browserCommand)
        self.surface = DrawingSurface(self.port) if project.version >= 2 else None
        self.pages = Pages(self) if self.surface else None
        if pending:
            self.pages.home_ready = False
            self.pages.retry_job = ("", project.brief, False, project.page(""))
            self.pages.message = "Main page unfinished. Select Retry to generate it."
        QQmlEngine.setObjectOwnership(self, QQmlEngine.ObjectOwnership.CppOwnership)

    @property
    def active_page(self):
        return self.pages.page if self.pages else self.project

    title = Property(str, lambda self: self.active_page.name, notify=changed)
    dirty = Property(bool, lambda self: self.project != self.saved or self.saved_pending != (not self.canSave), notify=changed)
    storageStatus = Property(str, lambda self: self.storage_message, notify=changed)
    hasBrowser = Property(bool, lambda self: self.active_page.browser, notify=changed)
    toolbarHeight = Property(int, lambda self: self.active_page.toolbarHeight, notify=changed)
    building = Property(bool, lambda self: bool(self.pages and self.pages.job), notify=changed)
    canBack = Property(bool, lambda self: bool(self.pages and self.pages.history), notify=changed)
    canRetry = Property(bool, lambda self: bool(self.pages and self.pages.retry_job), notify=changed)
    pageStatus = Property(str, lambda self: self.pages.message if self.pages else "", notify=changed)
    previewHeading = Property(str, lambda self: self.pages.preview_heading if self.pages else "", notify=changed)
    canSave = Property(bool, lambda self: not self.pages or self.pages.home_ready, notify=changed)
    source = Property(str, lambda self: self._html, notify=reloadSource)
    native = Property(bool, lambda self: self.project.version >= 2, constant=True)
    drawing = Property(QObject, lambda self: self.surface, constant=True)

    @Property(QObject, constant=True)
    def guestProfile(self):
        if self._guest is None:
            self._guest = profile(False, self)
        return self._guest

    @Property(QObject, constant=True)
    def webProfile(self):
        if self._web is None:
            self._web = profile(True, self)
        return self._web
    browserPort = Property(QObject, lambda self: self.port, constant=True)

    @Slot("QVariantMap")
    def updateBrowser(self, state):
        self.port.state = state
        self.port.stateChanged.emit(state)

    @Slot()
    def edit(self):
        if self.building:
            return
        result = self.board.draft(self.active_page, progressive=bool(self.pages))
        if isinstance(result, PageRequest):
            self.pages.client.base, self.pages.client.model = result.endpoint, result.model
            self.pages.start(self.pages.key, result.prompt, revision=True, draft=result.source)
        elif result:
            self.apply(result)

    @Slot()
    def back(self):
        if self.pages:
            self.pages.back()

    @Slot()
    def cancelPage(self):
        if self.pages:
            self.pages.cancel()

    @Slot()
    def retryPage(self):
        if self.pages:
            self.pages.retry()

    def apply(self, project):
        if isinstance(self.project, PagedProject):
            try:
                self.pages.install(self.pages.key, project)
            except ValueError as exc:
                self.board.error(str(exc))
                return
            self.pages.home_ready = True
            self.pages.message, self.pages.retry_job = "", None
            self.save()
            self.changed.emit()
            self.surface.load(project.script)
            return
        if self.surface:
            self.project = project
            self.save()
            self.changed.emit()
            self.surface.load(project.script)
            return
        if project == self.project:
            self.reloadSource.emit()
            return
        html = document(project)
        self.project, self._html = project, html
        self.save()
        self.changed.emit()
        self.reloadSource.emit()

    @Slot(result=bool)
    def save(self):
        if not self.dirty:
            return True
        previous = self.version
        try:
            self.version = self.board.library.store(self.project, not self.canSave, previous)
        except (sqlite3.Error, ValueError, OSError) as exc:
            self.storage_message = f"Library save failed. {exc}"
            self.changed.emit()
            return False
        self.saved, self.saved_pending = self.project, not self.canSave
        self.storage_message = ("Another session changed this app. Saved your edits as a library copy."
                                if previous and previous.app_id != self.version.app_id else "")
        self.changed.emit()
        return True

    @Slot(result=bool)
    def exportApp(self):
        if not self.canSave:
            return False
        name, _ = QFileDialog.getSaveFileName(None, "Export app", "", "AppBoard projects (*.appboard)")
        if not name:
            return False
        path = Path(name)
        if path.suffix.lower() != ".appboard":
            path = path.with_name(path.name + ".appboard")
            if path.exists() and not self.confirm_overwrite(path):
                return False
        try:
            self.project.save(path)
            return True
        except (OSError, ValueError) as exc:
            self.board.error(str(exc))
            return False

    def confirm_overwrite(self, path):
        return QMessageBox.question(None, "Replace file?", f"Replace the current contents of {path.name}?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes

    def may_close(self):
        if not self.dirty:
            return True
        choice = QMessageBox.question(None, "Save app?", f"Save changes to {self.title}?",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                      QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        return choice == QMessageBox.StandardButton.Discard or (choice == QMessageBox.StandardButton.Save and self.save())

    @Slot()
    def close(self):
        if self.may_close():
            if self.pages:
                self.pages.client.cancel()
            if self.surface:
                self.surface.stop()
            self.board.sessions.remove(self)
            self.removed.emit()


class Board(QObject):
    opened = Signal(QObject)

    def __init__(self, library_path=None):
        super().__init__()
        self.sessions = []
        if library_path is None:
            base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
            library_path = Path(base) / "library.sqlite3"
        self.library = Library(library_path)

    @staticmethod
    def error(message):
        QMessageBox.warning(None, "AppBoard", message)

    def draft(self, project, progressive=False):
        dialog = Editor(project, progressive=progressive)
        return dialog.result_project if dialog.exec() else None

    def choose_provider(self):
        dialog = QDialog()
        dialog.setWindowTitle("Choose a model for this page")
        form = QFormLayout(dialog)
        endpoint = QLineEdit(QSettings().value("generation/catalogEndpoint", "http://127.0.0.1:1234/v1"))
        picker = ModelPicker(endpoint, None, dialog)
        form.addRow("Configured server", endpoint)
        form.addRow("Model", picker)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(lambda: dialog.accept() if picker.combo.currentData() else None)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        accepted = dialog.exec()
        picker.cancel()
        return picker.combo.currentData() if accepted else None

    def mount(self, project, version=None, pending=False):
        session = Session(self, project, version, pending)
        if version is None:
            session.save()
        self.sessions.append(session)
        self.opened.emit(session)
        if session.surface:
            session.surface.load(project.script)
        return session

    @Slot()
    def create(self):
        draft = self.draft(DrawingProject(), progressive=True)
        if isinstance(draft, PageRequest):
            source = draft.source
            project = PagedProject(source.name, source.script, source.browser, source.toolbarHeight, brief=draft.prompt)
            session = self.mount(project, pending=True)
            session.pages.client.base, session.pages.client.model = draft.endpoint, draft.model
            session.pages.start("", draft.prompt, draft=draft.source)
        elif draft:
            self.mount(PagedProject(draft.name, draft.script, draft.browser, draft.toolbarHeight))

    @Slot()
    def open(self):
        try:
            dialog = LibraryDialog(self.library.entries())
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error(str(exc))
            return
        if dialog.exec():
            if dialog.importing:
                name, _ = QFileDialog.getOpenFileName(None, "Import app", "", "AppBoard projects (*.appboard);;All files (*)")
                if name:
                    self.open_path(Path(name))
            elif dialog.selected_id:
                self.open_record(dialog.selected_id)

    def open_record(self, app_id):
        for session in self.sessions:
            if session.version and session.version.app_id == app_id:
                session.activated.emit()
                return session
        try:
            project, pending, version = self.library.load(app_id)
            return self.mount(project, version, pending)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error(str(exc))

    def open_path(self, path):
        try:
            return self.mount(Project.load(path))
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    @Slot(QObject)
    def release(self, session):
        if session not in self.sessions:
            session.deleteLater()

    @Slot(result=bool)
    def mayExit(self):
        return all(session.may_close() for session in self.sessions)
