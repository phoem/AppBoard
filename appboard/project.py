"""The portable, versioned app project. Runtime state lives outside this file."""
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_BYTES = 512 * 1024
STARTER = """<!doctype html>
<meta charset="utf-8">
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { padding: 16px; }
</style>
<main></main>
<script>
  // Add app behavior here.
</script>
"""


class ProjectFile:
    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] not in (1, 2):
            raise ValueError("AppBoard supports project versions 1 and 2.")
        project_type = DrawingProject if data["version"] == 2 else Project
        if data.keys() - project_type.__dataclass_fields__.keys():
            raise ValueError("The project contains unknown fields.")
        name = data.get("name")
        field = project_type.source_field
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("Enter an app name between 1 and 100 characters.")
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"The app needs nonempty {field} source.")
        if type(data.get("browser", False)) is not bool:
            raise ValueError("The browser setting must be true or false.")
        height = data.get("toolbarHeight", 80)
        if type(height) is not int or not 32 <= height <= 400:
            raise ValueError("Toolbar height must be between 32 and 400.")
        project = project_type(**data)
        if len(project.encode()) > MAX_BYTES:
            raise ValueError("The project exceeds the 512 KiB size limit.")
        return project

    def encode(self):
        return (json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    @classmethod
    def load(cls, path):
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("The project exceeds the 512 KiB size limit.")
        return cls.parse(json.loads(raw))

    def save(self, path):
        Project.parse(asdict(self))
        path = Path(path)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".appboard-", delete=False) as out:
                temp = Path(out.name)
                out.write(self.encode())
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, path)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)


@dataclass(frozen=True)
class Project(ProjectFile):
    source_field = "html"
    name: str = "Untitled app"
    html: str = STARTER
    browser: bool = False
    toolbarHeight: int = 80
    version: int = 1


@dataclass(frozen=True)
class DrawingProject(ProjectFile):
    source_field = "script"
    name: str = "Untitled app"
    script: str = 'function draw(g, w, h) {\n  g.clear("#ffffff");\n}\n'
    browser: bool = False
    toolbarHeight: int = 80
    version: int = 2
