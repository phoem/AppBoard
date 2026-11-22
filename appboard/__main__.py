import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication

from .host import Board


def desktop(library_path=None):
    QtWebEngineQuick.initialize()
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("AppBoard")
    app.setOrganizationName("AppBoard")
    app.setStyle("Fusion")
    QQuickStyle.setStyle("Basic")
    board = Board(library_path)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("boardApi", board)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("ui") / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("AppBoard could not load its desktop window.")
    engine.window = engine.rootObjects()[0]
    return app, board, engine


def main():
    app, board, engine = desktop()
    for path in sys.argv[1:]:
        board.open_path(Path(path))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
