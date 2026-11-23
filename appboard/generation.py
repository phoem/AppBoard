"""Asynchronous chat-completions client. Credentials stay in the desktop host."""
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .project import MAX_BYTES, Project
from .collectionview import is_collection_request
from .pagestream import COLLECTION_SCHEMA, PAGE_SCHEMA, PageStream, action_page_schema
from .sequence import sequence_candidate

SCHEMA = json.loads((Path(__file__).with_name("assets") / "generation.schema.json").read_text(encoding="utf-8"))
DRAWING_SCHEMA = {**SCHEMA, "properties": {
    **{k: v for k, v in SCHEMA["properties"].items() if k != "html"},
    "version": {"type": "integer", "enum": [2]}, "script": {"type": "string"}
}, "required": ["version", "name", "browser", "toolbarHeight", "script"]}

DRAWING_API = """Coordinates are logical pixels from top left. Draw in order:
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

DRAWING_INSTRUCTIONS = """Create a working native 2D AppBoard app. Return version 2, name, script, browser, toolbarHeight.
script is plain JavaScript. Implement function draw(g,w,h) and optionally function input(e,g,w,h).
App-level variables persist until close or source reload. Render the full scene on each draw.
For example, a status display can keep let label='Ready';
function draw(g,w,h){g.clear('white');g.text(8,8,label,16,'black');}
function input(e,g,w,h){if(e.type==='down')label='Selected';}
The fourth argument of g.text is numeric font size; the fifth is color.
Use the requested interaction and exact text format. The host redraws automatically after input.
""" + DRAWING_API

INSTRUCTIONS = """Create or revise a runnable AppBoard project from the user's request.
Return only a JSON object with version:1, name (1-100 characters), html (one self-contained HTML document with inline CSS and JavaScript), browser (boolean), toolbarHeight (integer from 32 to 400).
Use the DOM, SVG, Canvas 2D or WebGL as appropriate. Implement real interactive behavior.
External resources, network access, imports, persistent web storage and host filesystem access are unavailable in the generated document.
For a web browser, set browser:true. Your HTML occupies the toolbar above a separate real browsing surface.
Use AppBoard.browser.navigate(url), back(), forward(), reload(), and subscribe(fn).
Subscribers receive {url,title,canGoBack,canGoForward,loading}. HTML cannot access the page DOM.
For all other apps use browser:false. Fit the available panel, use accessible controls and support resizing.
When revising an existing app preserve behavior and styling outside the requested changes."""

HOME_EXAMPLE = """Build the main page. For a deferred feature, give its button a brief describing
what the user can see and do there, including the shared data it should use. Prefix the brief with
"Browse collection:" only for a plain read-only list or thumbnail grid. Use a normal brief for custom features.
{"name":"Atlas","sections":["g.clear('white'); g.text(16,12,'Atlas',22);","g.featureButton(16,52,140,40,'Places','places','Browse collection: recorded places from g.data.places','teal');"],"browser":false,"toolbarHeight":80,"input":""}"""

COLLECTION_INSTRUCTIONS = """Describe the requested collection view as five JSON strings.
name is its visible heading. collection is the g.data array key from the brief or collectionKeys.
labelField names an item's title field. For a gallery set imageField to the thumbnail PNG field,
or use "" for text lists. emptyText is a short message when the collection is empty.
Example: {"name":"Roster","collection":"members","labelField":"name","imageField":"","emptyText":"No members yet."}
Use the requested names. The host handles layout, scrolling and native rendering."""

FEATURE_INSTRUCTIONS = """Write the requested page as short runnable JS fragments in one draw(g,w,h).
w,h are surface dimensions, g.data persists between events. Render output with g.text(x,y,value,size=16,color).
Actions belong directly inside draw: if(g.button(x,y,w,h,label,color)) { /* action */ }
For typing: const f=g.textField(x,y,w,h,key,placeholder); if(f.submitted) { /* use f.value */ }
Buttons and fields handle their own events. Use input:"" for these. For custom gestures only, input
can contain the separate input(e,g,w,h) body: e.type down/up/move/key/wheel, x,y,key,text,delta.
Drawing calls: g.clear(color), g.rect(x,y,w,h,color,radius=0), g.circle(cx,cy,r,color),
g.line(x1,y1,x2,y2,color,thickness), g.path(svgPath,fill,stroke,thickness), g.image(x,y,w,h,png), g.animate().
g.openFeature(id,brief) opens another AppBoard page. JavaScript math and arrays work normally.
For websites use browser:true: fit everything on one toolbar row inside toolbarHeight. Chromium shows
the site. Use if(f.submitted) g.browser.navigate(f.value); and if(g.button(...)) g.browser.back();
or g.browser.forward(). g.browser.reload(), url and title are available.
Example of a complete custom feature. Match the user's requested labels and behavior:
{"name":"Labels","sections":["g.clear('white'); g.text(8,8,'Labels',18);","const f=g.textField(8,40,w-150,32,'entry','Name'); if(f.submitted) g.data.label=f.value;","if(g.button(w-130,40,120,32,'Reset','teal')) g.data.label='';","g.text(8,88,g.data.label||'');"],"browser":false,"toolbarHeight":80,"input":""}
Keep each section short. For revisions, preserve other behavior and styling. Use the same direct
if(g.button(...)) pattern for ordinary buttons."""

SEQUENCE_INSTRUCTIONS = """Return the feature's name and layout. For a sequence edited by buttons, layout
contains key (shared array name), separator, append, remove_last, remove_first and clear.
The host draws every nonempty action label as a button and displays the entries in order with the exact separator.
append contains the additive choices only. For remove_last give the exact label for undoing the most recent entry;
remove_first is the label for taking the oldest entry; clear is the label for clearing all. Use "" for unrequested actions.
Each append choice has a label and value. When a choice adds its own name, use that name for both.
Copy the action names from the user's brief exactly. A field for an unrequested edit must be empty.
If behavior or styling requires more than an ordered list, layout can contain sections, browser, toolbarHeight
and input instead. Use ordinary JS sections inside draw(g,w,h)
and the separate input(e,g,w,h) body. g.data stores state. Native primitives include g.text, g.rect,
g.circle, g.line, g.button and g.textField."""

POINTER_INSTRUCTIONS = """Implement the requested interactive drawing in short JS fragments. The host
calls input(e,g,w,h) on events, then calls draw(g,w,h). Store coordinates in g.data across frames.
Put all pointer event code in the input string. Use e.type==='down' for a click and e.x,e.y for position.
For drags use move with e.buttons, and up on release. Use plain statements in input and in sections.
Example of the entire response for a position probe:
{"name":"Probe","sections":["g.clear('white'); g.text(8,8,'Probe');","if(g.data.mark) g.circle(g.data.mark.x,g.data.mark.y,4,'navy');"],"browser":false,"toolbarHeight":80,"input":"if(e.type==='down') g.data.mark={x:e.x,y:e.y};"}
Draw with g.clear(color), g.text(x,y,value,size,color), g.circle(cx,cy,r,color), g.line(x1,y1,x2,y2,color,thickness),
g.path(svgPath,fill,stroke,thickness) and g.rect(x,y,w,h,color). Standard Math and arrays work.
Keep the JS concise. The host handles event registration and repainting. Preserve other behavior on edits."""


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
    preview = Signal(str)
    partialPreview = Signal(str)
    pageTitle = Signal(str)

    def __init__(self, parent=None, base=None, model=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.configured_base = os.getenv("APPBOARD_MODEL_URL", "http://127.0.0.1:1234/v1").rstrip("/")
        self.base = (base or self.configured_base).rstrip("/")
        self.model = model if model is not None else os.getenv("APPBOARD_MODEL", "")
        self.reply = None
        self.fast_model = None
        self.can_skip_reasoning = False

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
                                               **({"temperature": 0.2} if native else {}),
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

    def generate_page(self, context):
        self.cancel()
        feature = context.get("pageKind") == "feature" or context.get("page", "main") != "main"
        collection = feature and is_collection_request(context)
        sequence = feature and not collection and sequence_candidate(context)
        collection_key = None
        instructions = """Write one working native page for the user's request. Output its name and drawing sections first.
Choose the name, heading and contents from the request. In drawing arrays each entry contains JS statements.
Keep sections short and terminate drawing calls with semicolons.
g IS the drawing API. Call its methods directly. g.ctx, fillStyle, canvas, DOM and function wrappers do not work.
Use g.featureButton only for navigation to a distinct subpage. After x,y,width,height supply
exactly four strings in order: visible label, ONE stable ID, descriptive brief, Qt color. It handles clicks.
Feature IDs start with a lowercase letter and use lowercase letters, digits, hyphens or underscores.
When feature buttons handle all interactions, return input as an empty string.
Implement only the requested page. Back is supplied. For other controls, input is the body of input(e,g,w,h).
Keep shared state in g.data. Show an empty state for empty collections. Add sample records only if requested.
Use concise code. Available primitives:
"""
        if collection:
            keys = context.get("collectionKeys", [])
            collection_key = keys[0] if len(keys) == 1 else context["page"]
            system_prompt = COLLECTION_INSTRUCTIONS
        elif feature:
            system_prompt = FEATURE_INSTRUCTIONS
            brief = context["request"]
            if ("fromPage" in context and not sequence and
                    re.search(r"\b(?:click|tap|drag)\w*\b", brief, re.I) and
                    re.search(r"\b(?:points?|coordinates?|drawing surface|canvas)\b", brief, re.I)):
                system_prompt = POINTER_INSTRUCTIONS
        else:
            system_prompt = HOME_EXAMPLE + "\nEach section runs in its own block inside draw(g,w,h).\n" + instructions + DRAWING_API
        def submit(fast=False, use_sequence=sequence):
            stream = PageStream(self.preview.emit, self.pageTitle.emit, self.partialPreview.emit,
                                shared_scope=feature, collection_key=collection_key, allow_sequence=use_sequence)
            prompt = system_prompt
            schema = COLLECTION_SCHEMA if collection else PAGE_SCHEMA
            if use_sequence:
                prompt = SEQUENCE_INSTRUCTIONS
                schema = action_page_schema(context["request"])
            payload = {"model": self.model, "temperature": 0.2, "stream": True,
                       "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(context)}],
                       "response_format": {"type": "json_schema", "json_schema": {
                           "name": "appboard_page", "strict": True, "schema": schema}}}
            if fast:
                payload["reasoning_effort"] = "none"

            def rejected(status, message):
                if use_sequence and status in (400, 422) and not stream.received:
                    submit(fast, False)
                elif fast and status in (400, 422) and not stream.received:
                    self.can_skip_reasoning = False
                    submit(False, use_sequence)
                else:
                    self.failed.emit(message)

            self._request("chat/completions", payload, lambda _: self.generated.emit(stream.finish()),
                          stream=stream, on_error=rejected)

        url = QUrl(self.base)
        if ("correction" in context or url.host() not in {"localhost", "127.0.0.1", "::1"} or
                url.port() != 1234 or url.path().rstrip("/") != "/v1"):
            submit()
            return
        identity = (self.base, self.model)
        if self.fast_model == identity:
            submit(self.can_skip_reasoning)
            return

        def capabilities(raw):
            catalog = json.loads(raw)
            self.can_skip_reasoning = any(
                item.get("key") == self.model and
                "off" in item.get("capabilities", {}).get("reasoning", {}).get("allowed_options", [])
                for item in catalog.get("models", []) if isinstance(item, dict))
            self.fast_model = identity
            submit(self.can_skip_reasoning)

        self._request("/api/v1/models", None, capabilities, timeout=750,
                      on_error=lambda status, message: submit())

    def _request(self, route, body, consume, timeout=120_000, stream=None, on_error=None):
        url = QUrl(self.base + "/").resolved(QUrl(route))
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
        def read():
            if self.reply is not reply:
                return
            if not stream:
                if reply.bytesAvailable() > limit:
                    reply.abort()
                return
            if reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) != 200:
                return
            try:
                stream.feed(bytes(reply.readAll()))
            except (ValueError, AttributeError, TypeError, RecursionError) as exc:
                self.cancel()
                self.failed.emit(str(exc))
        reply.readyRead.connect(read)

        def finished():
            reply.deleteLater()
            if self.reply is not reply:
                return
            read()
            if self.reply is not reply:
                return
            self.reply = None
            try:
                if (reply.error() != QNetworkReply.NetworkError.NoError or
                        reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) != 200):
                    raise ValueError(f"Model request failed ({reply.errorString()}). Check your model server and APPBOARD_MODEL_URL.")
                consume(bytes(reply.readAll()))
            except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
                if on_error:
                    on_error(reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute), str(exc))
                else:
                    self.failed.emit(str(exc))

        reply.finished.connect(finished)
