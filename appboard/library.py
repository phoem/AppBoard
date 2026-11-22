"""Local source library. One stable ID per app, one transaction per accepted change."""
import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from .project import PagedProject, Project


@dataclass(frozen=True)
class Version:
    app_id: str
    revision: int


class Library:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=0.5)) as db, db:
            schema = db.execute("PRAGMA user_version").fetchone()[0]
            if schema == 0:
                db.execute("""CREATE TABLE IF NOT EXISTS apps (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, name TEXT NOT NULL,
                    brief TEXT NOT NULL, pending INTEGER NOT NULL, source BLOB NOT NULL,
                    updated TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )""")
                db.execute("PRAGMA user_version = 1")
            elif schema != 1:
                raise ValueError("This library requires a newer version of AppBoard.")
            yield db

    def store(self, project, pending=False, version=None):
        Project.parse(asdict(project))
        if pending and not isinstance(project, PagedProject):
            raise ValueError("Only a progressive project can have an unfinished main page.")
        values = (project.name, getattr(project, "brief", ""), pending, project.encode())
        with self.connection() as db:
            if version:
                updated = db.execute("""UPDATE apps SET name=?, brief=?, pending=?, source=?,
                    revision=revision+1, updated=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                    WHERE id=? AND revision=?""", (*values, version.app_id, version.revision))
                if updated.rowcount:
                    return Version(version.app_id, version.revision + 1)
            # A concurrent editor has saved another version. Preserve both copies.
            app_id = uuid4().hex
            db.execute("INSERT INTO apps (id,revision,name,brief,pending,source) VALUES (?,1,?,?,?,?)",
                       (app_id, *values))
            return Version(app_id, 1)

    def entries(self):
        with self.connection() as db:
            db.row_factory = sqlite3.Row
            return db.execute("SELECT id,name,brief,pending,updated FROM apps ORDER BY updated DESC,rowid DESC").fetchall()

    def load(self, app_id):
        with self.connection() as db:
            row = db.execute("SELECT revision,pending,source FROM apps WHERE id=?", (app_id,)).fetchone()
        if row is None:
            raise ValueError("This app is no longer in the library.")
        revision, pending, source = row
        return Project.parse(json.loads(source)), bool(pending), Version(app_id, revision)
