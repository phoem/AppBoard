"""Asynchronous chat-completions client. Credentials stay in the desktop host."""
import json
import os
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .project import MAX_BYTES, Project

SCHEMA = json.loads((Path(__file__).with_name("assets") / "generation.schema.json").read_text(encoding="utf-8"))
DRAWING_SCHEMA = {**SCHEMA, "properties": {
    **{k: v for k, v in SCHEMA["properties"].items() if k != "html"},
    "version": {"type": "integer", "enum": [2]}, "script": {"type": "string"}
}, "required": ["version", "name", "browser", "toolbarHeight", "script"]}

DRAWING_INSTRUCTIONS = """Create a working native 2D AppBoard app. Return version 2, name, script, browser, toolbarHeight.
script is plain JavaScript. Implement function draw(g,w,h) and optionally function input(e,g,w,h).
App-level variables persist until close or source reload. Render the full scene on each draw.
Coordinates are logical pixels from top left. Draw in order:
g.clear(color); g.rect(x,y,width,height,color,radius=0); g.circle(centerX,centerY,radius,color);
g.line(x1,y1,x2,y2,color,thickness=1); g.text(x,y,value,size=16,color="#151918");
g.path(svgPathData,fillColor,strokeColor="transparent",thickness=1); g.image(x,y,w,h,pngDataURL).
Use Qt named colors, transparent or #RRGGBB. Up to 512 calls per frame.
For motion call g.animate() in draw and use Date.now() for elapsed time.
input receives e.type "down", "up", "move", "wheel" or "key"; pointer has x,y,buttons; wheel has delta;
key has text and Qt integer key. Implement hit testing and control behavior yourself in input.
Draw custom controls with the same primitives. No HTML, DOM, canvas, imports, OS, async, network or timers.
For a browser, set browser true and draw the toolbar for the separate live web page.
From input use g.browser.navigate(url), back(), forward(), reload(). Read g.browser.url and title.
For other apps use browser false and toolbarHeight 80. Preserve unrelated behavior when revising."""

INSTRUCTIONS = """Create or revise a runnable AppBoard project from the user's request.
Return only a JSON object with version:1, name (1-100 characters), html (one self-contained HTML document with inline CSS and JavaScript), browser (boolean), toolbarHeight (integer from 32 to 400).
Use the DOM, SVG, Canvas 2D or WebGL as appropriate. Implement real interactive behavior.
External resources, network access, imports, persistent web storage and host filesystem access are unavailable in the generated document.
For a web browser, set browser:true. Your HTML occupies the toolbar above a separate real browsing surface.
Use AppBoard.browser.navigate(url), back(), forward(), reload(), and subscribe(fn).
Subscribers receive {url,title,canGoBack,canGoForward,loading}. HTML cannot access the page DOM.
For all other apps use browser:false. Fit the available panel, use accessible controls and support resizing.
When revising an existing app preserve behavior and styling outside the requested changes."""


def parse_response(raw):
    envelope = json.loads(raw)
    try:
        content = envelope["choices"][0]["message"]["content"].strip()
        if content.startswith("```") and content.endswith("```"):
            content = content.split("\n", 1)[1][:-3].strip()
        return Project.parse(json.loads(content))
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise ValueError("The model returned an incomplete chat response.") from exc


class Generator(QObject):
    generated = Signal(object)
    failed = Signal(str)
    choices = Signal(list)

    def __init__(self, parent=None, base=None, model=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.configured_base = os.getenv("APPBOARD_MODEL_URL", "http://127.0.0.1:1234/v1").rstrip("/")
        self.base = (base or self.configured_base).rstrip("/")
        self.model = model if model is not None else os.getenv("APPBOARD_MODEL", "")
        self.reply = None

    def cancel(self):
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort()

    def list_models(self):
        self.cancel()
        self._request("models", None, lambda raw: self.choices.emit(self.model_names(raw)), timeout=6000)

    @staticmethod
    def model_names(raw):
        models = json.loads(raw).get("data")
        if not isinstance(models, list):
            raise ValueError("The server returned an invalid model list.")
        return sorted({m["id"] for m in models if isinstance(m, dict) and
                       isinstance(m.get("id"), str) and m["id"].strip()}, key=str.casefold)

    def generate(self, prompt, project):
        self.cancel()
        native = project.version == 2
        messages = [{"role": "system", "content": DRAWING_INSTRUCTIONS if native else INSTRUCTIONS},
                    {"role": "user", "content": json.dumps({"request": prompt, "currentProject": asdict(project)})}]
        def received(raw):
            result = parse_response(raw)
            if result.version != project.version:
                raise ValueError("The model returned the wrong app format. Try generating again.")
            self.generated.emit(result)

        def submit(model):
            self._request("chat/completions", {"model": model, "messages": messages, "stream": False,
                                               "response_format": {"type": "json_schema", "json_schema": {
                                                   "name": "appboard_project", "strict": True,
                                                   "schema": DRAWING_SCHEMA if native else SCHEMA}}}, received)

        def select(raw):
            names = self.model_names(raw)
            if not names:
                raise ValueError("Load a chat model in your server or set APPBOARD_MODEL.")
            if len(names) == 1:
                submit(names[0])
            else:
                self.choices.emit(names)

        if self.model:
            submit(self.model)
        else:
            self._request("models", None, select)

    def _request(self, route, body, consume, timeout=120_000):
        url = QUrl(self.base + "/" + route)
        if not url.host() or url.userInfo() or (url.scheme() != "https" and
                (url.scheme() != "http" or url.host() not in {"localhost", "127.0.0.1", "::1"})):
            self.failed.emit("Use a local HTTP or remote HTTPS model endpoint in APPBOARD_MODEL_URL.")
            return
        request = QNetworkRequest(url)
        request.setTransferTimeout(timeout)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setRawHeader(b"Content-Type", b"application/json")
        token = os.getenv("APPBOARD_MODEL_KEY")
        if token and self.base == self.configured_base:
            request.setRawHeader(b"Authorization", ("Bearer " + token).encode())
        reply = self.network.get(request) if body is None else self.network.post(request, json.dumps(body).encode())
        self.reply = reply
        limit = MAX_BYTES * 8
        reply.setReadBufferSize(limit + 1)
        reply.readyRead.connect(lambda: reply.abort() if reply.bytesAvailable() > limit else None)

        def finished():
            reply.deleteLater()
            if self.reply is not reply:
                return
            self.reply = None
            try:
                if (reply.error() != QNetworkReply.NetworkError.NoError or
                        reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) != 200):
                    raise ValueError(f"Model request failed ({reply.errorString()}). Check your model server and APPBOARD_MODEL_URL.")
                consume(bytes(reply.readAll()))
            except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
                self.failed.emit(str(exc))

        reply.finished.connect(finished)
