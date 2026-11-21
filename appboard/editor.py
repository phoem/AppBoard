import os
from dataclasses import asdict, dataclass, replace
import quickjs

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QVBoxLayout)

from .generation import Generator
from .modelpicker import ModelPicker
from .native import Drawing
from .project import Project


@dataclass(frozen=True)
class PageRequest:
    prompt: str
    source: object
    endpoint: str
    model: str


class Editor(QDialog):
    def __init__(self, project, parent=None, progressive=False):
        super().__init__(parent)
        self.setWindowTitle("AppBoard Studio")
        self.resize(820, 690)
        self.initial = self.result_project = project
        self.progressive = progressive
        self.generator = Generator(self)
        self.settings = QSettings()
        self.endpoint = QLineEdit(os.getenv("APPBOARD_MODEL_URL") or
                                  self.settings.value("generation/catalogEndpoint",
                                                      self.settings.value("generation/endpoint", self.generator.base)))
        preferred = (os.getenv("APPBOARD_MODEL_URL") or self.settings.value("generation/endpoint", self.endpoint.text()),
                     os.getenv("APPBOARD_MODEL") or self.settings.value("generation/model", ""))
        self.picker = ModelPicker(self.endpoint, preferred, self)
        self.generator.generated.connect(self.generated)
        self.generator.failed.connect(self.failed)
        self.prompt = QLineEdit(placeholderText="Describe a new app or a change to this draft")
        self.generate = QPushButton("Generate and run" if project.version == 2 else "Generate")
        self.generate.clicked.connect(self.start)
        self.prompt.returnPressed.connect(self.start)
        self.cancel_request = QPushButton("Stop")
        self.cancel_request.clicked.connect(self.stop)
        self.name = QLineEdit()
        self.name.setMaxLength(100)
        self.source = QPlainTextEdit()
        self.source.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.source.setTabChangesFocus(False)
        self.browser = QCheckBox("Attach a live web browsing pane")
        self.height = QSpinBox()
        self.height.setRange(32, 400)
        self.height.setSuffix(" px")
        self.browser.toggled.connect(self.height.setEnabled)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.run = buttons.addButton("Run app", QDialogButtonBox.ButtonRole.AcceptRole)
        self.run.setAutoDefault(False)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.apply)
        row = QHBoxLayout()
        for w in (self.prompt, self.generate, self.cancel_request):
            row.addWidget(w)
        form = QFormLayout()
        form.addRow("Configured server", self.endpoint)
        form.addRow("Model", self.picker)
        form.addRow("Name", self.name)
        form.addRow("Browser", self.browser)
        form.addRow("Toolbar height", self.height)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addLayout(form)
        layout.addWidget(QLabel("Native 2D drawing script" if project.version == 2 else "Source · HTML / CSS / JavaScript"))
        layout.addWidget(self.source, 1)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        self.fill(project)
        self.set_busy(False)
        self.prompt.setFocus()

    def fill(self, project):
        self.name.setText(project.name)
        self.source.setPlainText(getattr(project, project.source_field))
        self.browser.setChecked(project.browser)
        self.height.setValue(project.toolbarHeight)

    def draft(self):
        return replace(self.initial, name=self.name.text(), browser=self.browser.isChecked(),
                       toolbarHeight=self.height.value(), **{self.initial.source_field: self.source.toPlainText()})

    def set_busy(self, busy):
        for widget in (self.generate, self.name, self.source, self.browser, self.prompt, self.run,
                       self.endpoint, self.picker):
            widget.setEnabled(not busy)
        self.height.setEnabled(not busy and self.browser.isChecked())
        self.cancel_request.setVisible(busy)

    def start(self):
        if not self.prompt.text().strip() or not self.generate.isEnabled():
            return
        selected = self.picker.combo.currentData()
        if not selected:
            self.failed("Select a model. Check the endpoint and refresh if the list is empty.")
            return
        if self.progressive:
            self.generator.base, self.generator.model = selected
            self.remember_provider()
            self.result_project = PageRequest(self.prompt.text().strip(), self.draft(), *selected)
            self.accept()
            return
        self.set_busy(True)
        self.generator.base, self.generator.model = selected
        self.status.setText("Generating app…")
        self.generator.generate(self.prompt.text().strip(), self.draft())

    def stop(self):
        self.generator.cancel()
        self.failed("Generation stopped.")

    def remember_provider(self):
        self.settings.setValue("generation/catalogEndpoint", self.endpoint.text().strip().rstrip("/"))
        self.settings.setValue("generation/endpoint", self.generator.base)
        self.settings.setValue("generation/model", self.generator.model)

    def generated(self, project):
        self.remember_provider()
        self.fill(project)
        self.set_busy(False)
        if project.version == 2:
            self.apply()
        else:
            self.status.setText("Draft ready. Review the source or run the app.")

    def failed(self, message):
        self.set_busy(False)
        self.status.setText(message)

    def apply(self):
        try:
            self.result_project = Project.parse(asdict(self.draft()))
            if self.result_project.version == 2:
                Drawing(self.result_project.script).frame(640, self.height.value() if self.browser.isChecked() else 400)
        except (ValueError, quickjs.JSException, OverflowError, RecursionError) as exc:
            self.failed(str(exc))
            return
        self.accept()

    def done(self, result):
        self.picker.cancel()
        self.generator.cancel()
        super().done(result)

    def reject(self):
        if self.initial != self.draft() and QMessageBox.question(
                self, "Discard draft?", "Discard your edits to this draft?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard:
            return
        self.generator.cancel()
        super().reject()
