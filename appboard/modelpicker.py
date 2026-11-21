"""Discover accessible model IDs per server and retain their routing information."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .generation import Generator

LOCAL_SERVERS = {"http://127.0.0.1:1234/v1": "LM Studio", "http://127.0.0.1:11434/v1": "Ollama"}


class ModelPicker(QWidget):
    def __init__(self, endpoint, preferred, parent=None):
        super().__init__(parent)
        self.endpoint = endpoint
        self.preferred = preferred
        self.combo = QComboBox()
        self.combo.setPlaceholderText("Select a model")
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setAutoDefault(False)
        self.note = QLabel()
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setWordWrap(True)
        self.clients = {}
        self.results = {}
        self.failures = {}
        self.loaded = False
        row = QHBoxLayout()
        row.addWidget(self.combo, 1)
        row.addWidget(self.refresh_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.note)
        self.refresh_button.clicked.connect(self.refresh)
        self.debounce = QTimer(self, singleShot=True, interval=450)
        self.debounce.timeout.connect(self.refresh)
        self.endpoint.textEdited.connect(self.endpoint_edited)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loaded:
            self.refresh()

    def endpoint_edited(self):
        self.cancel()
        self.combo.clear()
        self.note.setText("Looking up models…")
        self.debounce.start()

    def cancel(self):
        self.debounce.stop()
        clients, self.clients = self.clients, {}
        for client in clients.values():
            client.cancel()
            client.deleteLater()

    def refresh(self):
        self.preferred = self.combo.currentData() or self.preferred
        self.cancel()
        self.loaded = True
        self.combo.clear()
        self.results.clear()
        self.failures.clear()
        self.note.setText("Looking up models…")
        servers = dict(LOCAL_SERVERS)
        custom = self.endpoint.text().strip().rstrip("/")
        if custom:
            servers.setdefault(custom, custom)
        # Register all clients before starting requests; an invalid URL can fail synchronously.
        self.clients = {base: Generator(self, base=base) for base in servers}
        for base, client in list(self.clients.items()):
            client.choices.connect(lambda names, b=base: self.finish(b, names))
            client.failed.connect(lambda error, b=base: self.finish(b, [], error))
            client.list_models()

    def finish(self, base, names, error=""):
        client = self.clients.pop(base, None)
        if client is None:
            return
        client.deleteLater()
        self.results[base] = names
        if error:
            self.failures[base] = error
        current = self.combo.currentData()
        self.combo.clear()
        for url, ids in sorted(self.results.items(), key=lambda item: LOCAL_SERVERS.get(item[0], item[0])):
            for model in ids:
                self.combo.addItem(f"{LOCAL_SERVERS.get(url, url)}  ·  {model}", (url, model))
        selected = current or self.preferred
        idx = next((i for i in range(self.combo.count()) if self.combo.itemData(i) == selected), -1)
        if idx < 0 and self.combo.count() == 1 and not self.clients:
            idx = 0
        self.combo.setCurrentIndex(idx)
        self.combo.setPlaceholderText(f"Choose from {self.combo.count()} models" if self.combo.count() else "Select a model")
        details = []
        if self.clients:
            details.append("Looking up models…")
        if self.failures:
            details.append("Unavailable: " + ", ".join(LOCAL_SERVERS.get(url, url) for url in self.failures))
        if not self.clients and not self.combo.count():
            details.append("Start a model server or check its endpoint, then refresh.")
        self.note.setText(" ".join(details))
        self.note.setToolTip("\n".join(self.failures.values()))
