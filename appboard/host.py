import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtQml import QQmlEngine

from PySide6.QtWidgets import QFileDialog, QMessageBox

from .editor import Editor
from .project import Project
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
        if not self.session.project.browser:
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
    browserCommand = Signal(str, str)

    def __init__(self, board, project, path=None):
        super().__init__(board)
        self.board, self.project, self.path = board, project, path
        self.saved = project if path else None
        self.fingerprint = self.digest(path) if path else None
        self._html = document(project)
        self._guest = profile(False, self)
        self._web = profile(True, self)
        self.port = BrowserPort(self)
        self.port.command.connect(self.browserCommand)
        QQmlEngine.setObjectOwnership(self, QQmlEngine.ObjectOwnership.CppOwnership)

    @staticmethod
    def digest(path):
        with Path(path).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").digest()

    title = Property(str, lambda self: self.project.name, notify=changed)
    dirty = Property(bool, lambda self: self.project != self.saved, notify=changed)
    hasBrowser = Property(bool, lambda self: self.project.browser, notify=changed)
    toolbarHeight = Property(int, lambda self: self.project.toolbarHeight, notify=changed)
    source = Property(str, lambda self: self._html, notify=reloadSource)
    guestProfile = Property(QObject, lambda self: self._guest, constant=True)
    webProfile = Property(QObject, lambda self: self._web, constant=True)
    browserPort = Property(QObject, lambda self: self.port, constant=True)

    @Slot("QVariantMap")
    def updateBrowser(self, state):
        self.port.state = state
        self.port.stateChanged.emit(state)

    @Slot()
    def edit(self):
        if project := self.board.draft(self.project):
            self.apply(project)

    def apply(self, project):
        if project == self.project:
            self.reloadSource.emit()
            return
        html = document(project)
        self.project, self._html = project, html
        self.changed.emit()
        self.reloadSource.emit()

    @Slot(result=bool)
    def save(self):
        path = self.path
        if path is None:
            name, _ = QFileDialog.getSaveFileName(None, "Save app", "", "AppBoard projects (*.appboard)")
            if not name:
                return False
            path = Path(name)
            if not path.suffix:
                path = path.with_suffix(".appboard")
                if path.exists() and not self.confirm_overwrite(path):
                    return False
        try:
            if path == self.path and path.exists() and self.digest(path) != self.fingerprint:
                if not self.confirm_overwrite(path):
                    return False
            self.project.save(path)
            self.path, self.saved = path, self.project
            self.fingerprint = hashlib.sha256(self.project.encode()).digest()
            self.changed.emit()
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
            self.board.sessions.remove(self)
            self.removed.emit()


class Board(QObject):
    opened = Signal(QObject)

    def __init__(self):
        super().__init__()
        self.sessions = []

    @staticmethod
    def error(message):
        QMessageBox.warning(None, "AppBoard", message)

    def draft(self, project):
        dialog = Editor(project)
        return dialog.result_project if dialog.exec() else None

    def mount(self, project, path=None):
        session = Session(self, project, path)
        self.sessions.append(session)
        self.opened.emit(session)
        return session

    @Slot()
    def create(self):
        if project := self.draft(Project()):
            self.mount(project)

    @Slot()
    def open(self):
        name, _ = QFileDialog.getOpenFileName(None, "Open app", "", "AppBoard projects (*.appboard);;All files (*)")
        if name:
            self.open_path(Path(name))

    def open_path(self, path):
        try:
            return self.mount(Project.load(path), path)
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    @Slot(QObject)
    def release(self, session):
        if session not in self.sessions:
            session.deleteLater()

    @Slot(result=bool)
    def mayExit(self):
        return all(session.may_close() for session in self.sessions)
