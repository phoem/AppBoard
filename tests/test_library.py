import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path

from appboard.library import Library
from appboard.project import DrawingProject, PagedProject, Project


class LibraryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.library = Library(self.folder / "data" / "library.sqlite3")

    def test_portable_copy_opens_in_a_different_library(self):
        page = DrawingProject("Birds", "function draw(g){g.text(4,4,'Heron')}")
        for project in (Project("Notes"), page, PagedProject("Habitat", features={"birds": asdict(page)})):
            with self.subTest(format=project.version):
                version = self.library.store(project)
                restored, pending, reopened = Library(self.library.path).load(version.app_id)
                self.assertFalse(pending)
                self.assertEqual(reopened, version)
                file = self.folder / "shared.appboard"
                restored.save(file)
                recipient = Library(self.folder / "recipient.sqlite3")
                imported = recipient.store(Project.load(file))
                self.assertNotEqual(version.app_id, imported.app_id)
                self.assertEqual(recipient.load(imported.app_id)[0], project)

    def test_concurrent_edit_keeps_both_versions_and_rejects_invalid_update(self):
        first = self.library.store(PagedProject("Original"))
        other = Library(self.library.path)
        original, _, stale = other.load(first.app_id)
        current = self.library.store(replace(original, name="Mine"), version=first)
        fork = other.store(replace(original, name="Yours"), version=stale)
        self.assertEqual(current.app_id, first.app_id)
        self.assertNotEqual(current.app_id, fork.app_id)
        with self.assertRaises(ValueError):
            self.library.store(replace(original, script=""), version=current)
        self.assertEqual(self.library.load(current.app_id)[0].name, "Mine")
        self.assertEqual(other.load(fork.app_id)[0].name, "Yours")
        self.assertEqual(len(other.entries()), 2)

    def test_future_library_schema_is_preserved(self):
        self.library.store(Project("Keep"))
        with closing(sqlite3.connect(self.library.path)) as db:
            db.execute("PRAGMA user_version=2")
        with self.assertRaisesRegex(ValueError, "newer version"):
            self.library.store(Project("Replace"))
        with closing(sqlite3.connect(self.library.path)) as db:
            self.assertEqual(db.execute("SELECT name FROM apps").fetchall(), [("Keep",)])
