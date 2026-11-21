import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from appboard.generation import parse_response
from appboard.project import MAX_BYTES, Project
from appboard.runtime import navigation_url


class ProjectTests(unittest.TestCase):
    def test_unicode_round_trip_and_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "example.appboard"
            Project().save(path)
            project = Project("Météo", "<p>☀</p>", True, 120)
            project.save(path)
            self.assertEqual(Project.load(path), project)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_failed_replace_preserves_saved_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "example.appboard"
            Project().save(path)
            with patch("appboard.project.os.replace", side_effect=PermissionError), self.assertRaises(PermissionError):
                Project("Revised").save(path)
            self.assertEqual(Project.load(path), Project())
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_rejects_invalid_or_future_projects(self):
        valid = json.loads(Project().encode())
        for field, value in (("version", 2), ("version", True), ("browser", "yes"), ("name", ""),
                             ("html", " "), ("toolbarHeight", 999), ("extra", None)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                Project.parse({**valid, field: value})

    def test_size_limit_on_disk_and_in_editor(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "huge.appboard"
            path.write_bytes(b"x" * (MAX_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "size"):
                Project.load(path)
            with self.assertRaisesRegex(ValueError, "size"):
                Project("Huge", "x" * MAX_BYTES).save(path)

    def test_chat_response(self):
        project = Project()
        content = "```json\n" + project.encode().decode() + "```"
        self.assertEqual(parse_response(json.dumps({"choices": [{"message": {"content": content}}]})), project)
        for raw in (b"{}", b"null", b"bad", b'{"choices":[]}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_response(raw)

    def test_navigation_contract(self):
        self.assertEqual(navigation_url("https://example.org/test"), "https://example.org/test")
        for value in ("file:///C:/", "data:text/plain,test", "javascript:void(0)", "https://user:pw@example.org/"):
            self.assertEqual(navigation_url(value), "")
