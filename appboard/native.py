"""Bounded JavaScript logic and typed frames for the native Qt Quick renderer."""
import base64
import binascii
import json
import math
import struct
from pathlib import Path

import quickjs
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QColor
from .project import FEATURE_ID

SDK = (Path(__file__).with_name("assets") / "drawing.js").read_text(encoding="utf-8")
FIELDS = {
    "rect": ("x", "y", "w", "h", "color", "radius"),
    "text": ("x", "y", "value", "size", "color"),
    "path": ("d", "color", "stroke", "thickness"),
    "image": ("x", "y", "w", "h", "png"),
}


def validate_png(value):
    prefix = "data:image/png;base64,"
    if not isinstance(value, str) or not value.startswith(prefix) or len(value) > 400_000:
        raise ValueError("image() needs an embedded PNG data URL up to 400,000 characters.")
    try:
        header = base64.b64decode(value[len(prefix):len(prefix)+32], validate=True)
        if header[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
            width, height = struct.unpack(">II", header[16:24])
            if 0 < width <= 2048 and 0 < height <= 2048:
                return
    except (binascii.Error, struct.error):
        pass
    raise ValueError("image() requires a PNG up to 2048 × 2048.")


def checked_frame(raw):
    if not isinstance(raw, str) or len(raw) > 600_000:
        raise ValueError("The drawing frame exceeds its size budget.")
    frame = json.loads(raw)
    if not isinstance(frame, dict) or type(frame.get("animate")) is not bool:
        raise ValueError("Invalid drawing frame.")
    nodes = frame.get("nodes")
    if not isinstance(nodes, list) or len(nodes) > 512:
        raise ValueError("A frame supports up to 512 drawing operations.")
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("kind"), str):
            raise ValueError("Invalid drawing operation.")
        fields = FIELDS.get(node["kind"])
        if fields is None or set(node) != {"kind", *fields}:
            raise ValueError(f"Invalid arguments for {node['kind']}.")
        for key in fields:
            value = node[key]
            if key in ("color", "stroke"):
                if not isinstance(value, str) or len(value) > 32 or not QColor.isValidColorName(value):
                    raise ValueError(f"Invalid Qt color for {key}. Use #RRGGBB or a named color.")
            elif key in ("d", "value"):
                if not isinstance(value, str) or len(value) > 8192:
                    raise ValueError("Text and path strings are limited to 8192 characters.")
            elif key == "png":
                validate_png(value)
            elif type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 65536:
                raise ValueError(f"{key} needs a finite coordinate within ±65536.")
            elif key in ("size", "thickness") and not 0 <= value <= 512:
                raise ValueError(f"{key} must be between 0 and 512.")
    commands = frame.get("commands")
    if not isinstance(commands, list) or len(commands) > 16:
        raise ValueError("Too many browser commands in one frame.")
    for cmd in commands:
        if (not isinstance(cmd, list) or len(cmd) != 2 or cmd[0] not in ("navigate", "back", "forward", "reload")
                or not isinstance(cmd[1], str) or len(cmd[1]) > 8192):
            raise ValueError("Invalid browser command.")
    feature = frame.get("feature")
    if feature is not None and (not isinstance(feature, list) or len(feature) != 2 or
            not isinstance(feature[0], str) or not FEATURE_ID.fullmatch(feature[0]) or
            not isinstance(feature[1], str) or not 0 < len(feature[1].strip()) <= 2048):
        raise ValueError("openFeature needs a stable lowercase ID and a short feature description.")
    if not isinstance(frame.get("data", {}), dict) or len(json.dumps(frame.get("data", {}))) > 65536:
        raise ValueError("Shared app data must be an object up to 64 KiB.")
    return frame


class Drawing:
    def __init__(self, script):
        self.vm = quickjs.Context()
        self.vm.set_memory_limit(16 * 1024 * 1024)
        self.vm.set_time_limit(0.05)
        self.vm.set_max_stack_size(256 * 1024)
        self.render = self.vm.eval(SDK)
        self.vm.eval(script)

    def frame(self, width, height, event=None, browser=None, data=None):
        raw = self.render(width, height, json.dumps(event) if event else "", json.dumps(browser or {}), json.dumps(data or {}))
        return checked_frame(raw)


class DrawingSurface(QObject):
    frameChanged = Signal()
    errorChanged = Signal()
    featureRequested = Signal(str, str)

    def __init__(self, port):
        super().__init__(port)
        self.port = port
        self.drawing = None
        self.size = (640, 400)
        self.nodes = []
        self.error = ""
        self.data = {}
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self.redraw)
        self.port.stateChanged.connect(self.schedule)

    items = Property("QVariantList", lambda self: self.nodes, notify=frameChanged)
    problem = Property(str, lambda self: self.error, notify=errorChanged)

    def load(self, script):
        self.stop()
        self.error = ""
        self.errorChanged.emit()
        try:
            self.drawing = Drawing(script)
            self.redraw()
        except (ValueError, quickjs.JSException) as exc:
            self.fail(exc)

    def stop(self):
        self.timer.stop()
        self.drawing = None

    def fail(self, exc):
        self.stop()
        self.error = (str(exc).partition("\n")[0] or "Drawing failed.")[:300]
        self.errorChanged.emit()

    def schedule(self):
        if self.drawing and not self.timer.isActive():
            self.timer.start(0)

    @Slot(int, int)
    def resize(self, width, height):
        size = max(1, width), max(1, height)
        if self.size != size:
            self.size = size
            self.schedule()

    @Slot("QVariantMap")
    def interact(self, event):
        self.redraw(event)

    def redraw(self, event=None):
        if not self.drawing:
            return
        try:
            frame = self.drawing.frame(*self.size, event, self.port.state, self.data)
        except (ValueError, quickjs.JSException, OverflowError, RecursionError) as exc:
            self.fail(exc)
            return
        self.data = frame["data"]
        if self.nodes != frame["nodes"]:
            self.nodes = frame["nodes"]
            self.frameChanged.emit()
        for action, value in frame["commands"]:
            self.port.request(action, value)
        if frame["animate"]:
            self.timer.start(16)
        if frame["feature"] and event and event.get("type") in ("down", "up", "key"):
            self.featureRequested.emit(*frame["feature"])
