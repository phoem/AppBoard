from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLabel, QLineEdit,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)


class LibraryDialog(QDialog):
    def __init__(self, entries):
        super().__init__()
        self.setWindowTitle("App library")
        self.resize(650, 430)
        self.importing = False
        self.filter = QLineEdit(placeholderText="Search names and prompts")
        self.apps = QTreeWidget()
        self.apps.setRootIsDecorated(False)
        self.apps.setHeaderLabels(["App", "Last saved"])
        self.apps.header().setStretchLastSection(False)
        self.apps.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for entry in entries:
            name = entry["name"]
            if entry["pending"]:
                if name == "Untitled app" and entry["brief"]:
                    name = entry["brief"]
                name += " (unfinished)"
            date = QDateTime.fromString(entry["updated"], Qt.DateFormat.ISODateWithMs).toLocalTime()
            item = QTreeWidgetItem(self.apps, [name, date.toString("yyyy-MM-dd HH:mm")])
            item.setData(0, Qt.ItemDataRole.UserRole, entry["id"])
            item.setToolTip(0, entry["brief"])
        self.apps.resizeColumnToContents(1)
        self.empty = QLabel()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        self.open_button = buttons.button(QDialogButtonBox.StandardButton.Open)
        self.import_button = buttons.addButton("Import .appboard…", QDialogButtonBox.ButtonRole.ActionRole)
        self.import_button.clicked.connect(self.choose_import)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.apps.itemDoubleClicked.connect(lambda *_: self.accept())
        self.filter.textChanged.connect(self.search)
        layout = QVBoxLayout(self)
        for widget in (self.filter, self.apps, self.empty, buttons):
            layout.addWidget(widget)
        self.search("")
        self.filter.setFocus()

    def search(self, query):
        query = query.strip().casefold()
        first = None
        for index in range(self.apps.topLevelItemCount()):
            item = self.apps.topLevelItem(index)
            visible = query in (item.text(0) + " " + item.toolTip(0)).casefold()
            item.setHidden(not visible)
            if visible and first is None:
                first = item
        self.apps.setCurrentItem(first)
        self.open_button.setEnabled(first is not None)
        self.empty.setText("No matching apps." if self.apps.topLevelItemCount() else "Your saved apps will appear here.")
        self.empty.setVisible(first is None)

    def choose_import(self):
        self.importing = True
        self.accept()

    @property
    def selected_id(self):
        item = self.apps.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None
