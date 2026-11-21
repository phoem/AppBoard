import os
from dataclasses import asdict

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QVBoxLayout)

from .generation import Generator
from .project import Project


class Editor(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AppBoard Studio")
        self.resize(820, 690)
        self.initial = self.result_project = project
        self.generator = Generator(self)
        self.settings = QSettings()
        self.endpoint = QLineEdit(os.getenv("APPBOARD_MODEL_URL") or
                                  self.settings.value("generation/endpoint", self.generator.base))
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.lineEdit().setPlaceholderText("Discover models or enter a model ID")
        self.model.setEditText(os.getenv("APPBOARD_MODEL") or self.settings.value("generation/model", ""))
        self.generator.choices.connect(self.choose_model)
        self.generator.generated.connect(self.generated)
        self.generator.failed.connect(self.failed)
        self.prompt = QLineEdit(placeholderText="Describe a new app or a change to this draft")
        self.generate = QPushButton("Generate")
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
        form.addRow("Model endpoint", self.endpoint)
        form.addRow("Model", self.model)
        form.addRow("Name", self.name)
        form.addRow("Browser", self.browser)
        form.addRow("Toolbar height", self.height)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addLayout(form)
        layout.addWidget(QLabel("Source · HTML / CSS / JavaScript"))
        layout.addWidget(self.source, 1)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        self.fill(project)
        self.set_busy(False)
        self.prompt.setFocus()

    def fill(self, project):
        self.name.setText(project.name)
        self.source.setPlainText(project.html)
        self.browser.setChecked(project.browser)
        self.height.setValue(project.toolbarHeight)

    def draft(self):
        return Project(name=self.name.text(), html=self.source.toPlainText(),
                       browser=self.browser.isChecked(), toolbarHeight=self.height.value())

    def set_busy(self, busy):
        for widget in (self.generate, self.name, self.source, self.browser, self.prompt, self.run,
                       self.endpoint, self.model):
            widget.setEnabled(not busy)
        self.height.setEnabled(not busy and self.browser.isChecked())
        self.cancel_request.setVisible(busy)

    def start(self):
        if not self.prompt.text().strip() or not self.generate.isEnabled():
            return
        self.set_busy(True)
        self.generator.base = self.endpoint.text().strip().rstrip("/")
        self.generator.model = self.model.currentText().strip()
        self.status.setText("Generating a draft…")
        self.generator.generate(self.prompt.text().strip(), self.draft())

    def stop(self):
        self.generator.cancel()
        self.failed("Generation stopped.")

    def generated(self, project):
        self.settings.setValue("generation/endpoint", self.generator.base)
        self.settings.setValue("generation/model", self.generator.model)
        self.fill(project)
        self.set_busy(False)
        self.status.setText("Draft ready. Review the source or run the app.")

    def choose_model(self, names):
        self.model.clear()
        self.model.addItems(names)
        self.model.setCurrentIndex(-1)
        self.set_busy(False)
        self.status.setText("Choose a chat model, then select Generate.")
        self.model.showPopup()

    def failed(self, message):
        self.set_busy(False)
        self.status.setText(message)

    def apply(self):
        try:
            self.result_project = Project.parse(asdict(self.draft()))
        except ValueError as exc:
            self.failed(str(exc))
            return
        self.accept()

    def reject(self):
        if self.initial != self.draft() and QMessageBox.question(
                self, "Discard draft?", "Discard your edits to this draft?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard:
            return
        self.generator.cancel()
        super().reject()
