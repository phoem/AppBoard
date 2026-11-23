"""Decode chat SSE and publish each complete drawing section exactly once."""
import json

from .project import MAX_BYTES, Project
from .collectionview import COLLECTION_FIELDS, collection_script

PAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "sections": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 32},
        "browser": {"type": "boolean"},
        "toolbarHeight": {"type": "integer", "minimum": 32, "maximum": 400},
        "input": {"type": "string"},
    },
    "required": ["name", "sections", "browser", "toolbarHeight", "input"],
    "additionalProperties": False,
}

COLLECTION_SCHEMA = {"type": "object", "properties": {k: {"type": "string"} for k in ("name", *COLLECTION_FIELDS)},
                     "required": ["name", *COLLECTION_FIELDS], "additionalProperties": False}


def page_script(sections, handler="", *, shared_scope=False):
    body = ("\n".join(sections) if shared_scope else
            "\n".join("{\n" + section + "\n}" for section in sections if section.strip()))
    return "function draw(g,w,h) {\n" + body + "\n}\nfunction input(e,g,w,h) {\n" + handler + "\n}\n"


class SectionReader:
    """Track JSON nesting across deltas without evaluating incomplete strings."""
    def __init__(self):
        self.depth = 0
        self.token = None
        self.escaped = False
        self.previous = ""
        self.key = None
        self.in_sections = False
        self.sections = []
        self.name = None
        self.statement_end = 0
        self.collection = {}

    def append(self, text):
        for char in text:
            if self.token is not None:
                self.token.append(char)
                if self.escaped:
                    self.escaped = False
                elif char == "\\":
                    self.escaped = True
                elif char == '"':
                    value = json.loads("".join(self.token))
                    if self.in_sections and self.depth == 2:
                        if len(self.sections) == 32:
                            raise ValueError("Too many drawing sections.")
                        self.sections.append(value)
                    elif self.depth == 1 and self.key == "name" and self.previous == ":":
                        self.name = value
                    elif self.depth == 1 and self.key in COLLECTION_FIELDS and self.previous == ":":
                        self.collection[self.key] = value
                    elif self.depth == 1 and self.previous in ("{", ","):
                        self.key = value
                    self.token = None
                    self.previous = '"'
                    self.statement_end = 0
                elif char == ";" and self.in_sections and self.depth == 2 and len(self.token) <= 4096:
                    self.statement_end = len(self.token)
                continue
            if char.isspace():
                continue
            if char == '"':
                self.token = ['"']
                continue
            if char in "[{":
                if self.depth == 1 and char == "[" and self.key == "sections" and self.previous == ":":
                    self.in_sections = True
                self.depth += 1
            elif char in "]}":
                if self.depth == 2:
                    self.in_sections = False
                self.depth -= 1
            self.previous = char


class PageStream:
    def __init__(self, preview, title=None, partial=None, *, shared_scope=False, collection_key=None):
        self.preview = preview
        self.title = title
        self.partial = partial
        self.partial_count = 0
        self.shared_scope = shared_scope
        self.collection_key = collection_key
        self.pending = bytearray()
        self.lines = []
        self.parts = []
        self.size = 0
        self.received = 0
        self.reader = SectionReader()
        self.complete = False

    def feed(self, chunk):
        self.received += len(chunk)
        if self.received > MAX_BYTES * 24:
            raise ValueError("Model stream exceeded its transport limit.")
        self.pending.extend(chunk)
        before = len(self.reader.sections)
        previous_fields = len(self.reader.collection)
        prior_end = self.reader.statement_end
        previous_name = self.reader.name
        lines = self.pending.split(b"\n")
        self.pending = lines.pop()
        for line in lines:
            self.line(line.rstrip(b"\r"))
        if (self.title and not before and self.reader.name != previous_name and
                isinstance(self.reader.name, str) and 0 < len(self.reader.name.strip()) <= 100):
            self.title(self.reader.name)
        if len(self.reader.sections) > before:
            self.preview(page_script(self.reader.sections, shared_scope=self.shared_scope))
        elif (self.collection_key is not None and self.reader.name and
              len(self.reader.collection) == len(COLLECTION_FIELDS) and
              (previous_fields != len(COLLECTION_FIELDS) or self.reader.name != previous_name)):
            self.preview(collection_script(self.reader.name, self.reader.collection, default_key=self.collection_key))
        elif (self.partial and self.reader.statement_end > prior_end and self.partial_count < 32):
            # Try a bounded prefix only in a disposable preview VM. A semicolon
            # can occur in a JS literal or an unfinished block, so failure is normal.
            raw = "".join(self.reader.token[:self.reader.statement_end]) + '"'
            section = json.loads(raw)
            self.partial_count += 1
            self.partial(page_script([*self.reader.sections, section], shared_scope=self.shared_scope))

    def line(self, line):
        if line.startswith(b"data:"):
            self.lines.append(line[5:].lstrip(b" "))
        elif not line and self.lines:
            raw = b"\n".join(self.lines)
            self.lines.clear()
            if raw == b"[DONE]":
                self.complete = True
                return
            msg = json.loads(raw)
            if msg.get("error"):
                raise ValueError("The model server reported a streaming error.")
            for choice in msg.get("choices", [])[:1]:
                reason = choice.get("finish_reason")
                if reason and reason != "stop":
                    raise ValueError(f"Page generation ended early ({reason}).")
                self.complete |= reason == "stop"
                value = choice.get("delta", {}).get("content")
                if value:
                    if not isinstance(value, str):
                        raise ValueError("Expected a text delta from the model.")
                    self.size += len(value)
                    if self.size > MAX_BYTES:
                        raise ValueError("Generated page exceeds the project size limit.")
                    self.parts.append(value)
                    self.reader.append(value)

    def finish(self):
        if self.pending:
            self.line(bytes(self.pending).rstrip(b"\r"))
        self.line(b"")
        if not self.complete:
            raise ValueError("The page stream was interrupted. Retry generation.")
        page = json.loads("".join(self.parts))
        schema = COLLECTION_SCHEMA if self.collection_key is not None else PAGE_SCHEMA
        if not isinstance(page, dict) or set(page) != set(schema["required"]):
            raise ValueError("Incomplete generated page.")
        if self.collection_key is not None:
            view = {k: page[k] for k in COLLECTION_FIELDS}
            script = collection_script(page["name"], view, default_key=self.collection_key)
            return Project.parse({"version": 2, "name": page["name"], "script": script})
        sections = page["sections"]
        if (not isinstance(sections, list) or not 1 <= len(sections) <= 32 or
                not all(isinstance(s, str) for s in sections) or not any(s.strip() for s in sections)
                or not isinstance(page["input"], str)):
            raise ValueError("Invalid drawing sections or input handler.")
        script = page_script(sections, page["input"], shared_scope=self.shared_scope)
        return Project.parse({"version": 2, "name": page["name"], "browser": page["browser"],
                              "toolbarHeight": page["toolbarHeight"], "script": script})
