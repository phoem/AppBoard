"""Asynchronous chat-completions client. Credentials stay in the desktop host."""
import json
import os
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .project import MAX_BYTES, Project

SCHEMA = json.loads((Path(__file__).with_name("assets") / "generation.schema.json").read_text(encoding="utf-8"))

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

    def generate(self, prompt, project):
        self.cancel()
        messages = [{"role": "system", "content": INSTRUCTIONS},
                    {"role": "user", "content": json.dumps({"request": prompt, "currentProject": asdict(project)})}]
        def submit(model):
            self._request("chat/completions", {"model": model, "messages": messages, "stream": False,
                                               "response_format": {"type": "json_schema", "json_schema": {
                                                   "name": "appboard_project", "strict": True, "schema": SCHEMA}}},
                          lambda raw: self.generated.emit(parse_response(raw)))

        def select(raw):
            models = json.loads(raw).get("data")
            names = [m["id"] for m in models or [] if isinstance(m, dict) and isinstance(m.get("id"), str)]
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

    def _request(self, route, body, consume):
        url = QUrl(self.base + "/" + route)
        if not url.host() or url.userInfo() or (url.scheme() != "https" and
                (url.scheme() != "http" or url.host() not in {"localhost", "127.0.0.1", "::1"})):
            self.failed.emit("Use a local HTTP or remote HTTPS model endpoint in APPBOARD_MODEL_URL.")
            return
        request = QNetworkRequest(url)
        request.setTransferTimeout(120_000)
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
