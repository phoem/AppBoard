"""The portable, versioned app project. Runtime state lives outside this file."""
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_BYTES = 512 * 1024
FEATURE_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}")
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
        types = {1: Project, 2: DrawingProject, 3: PagedProject}
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] not in types:
            raise ValueError("Unsupported AppBoard project version.")
        project_type = types[data["version"]]
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
        if project_type is PagedProject:
            brief, features = data.get("brief", ""), data.get("features", {})
            if not isinstance(brief, str) or not isinstance(features, dict) or len(features) > 64:
                raise ValueError("Invalid page brief or feature collection (maximum 64 features).")
            for key, page in features.items():
                if (not FEATURE_ID.fullmatch(key) or not isinstance(page, dict) or page.get("version") != 2):
                    raise ValueError("Invalid saved feature page.")
                cls.parse(page)
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


@dataclass(frozen=True)
class PagedProject(DrawingProject):
    version: int = 3
    brief: str = ""
    features: dict = field(default_factory=dict)

    def page(self, key):
        if key:
            return DrawingProject(**self.features[key])
        return DrawingProject(self.name, self.script, self.browser, self.toolbarHeight)
