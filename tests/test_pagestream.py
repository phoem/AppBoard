import json
import unittest

from appboard.pagestream import PageStream
from appboard.project import DrawingProject, PagedProject, Project
from dataclasses import asdict


def event(text):
    payload = {"choices": [{"delta": {"content": text}}]}
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\r\n\r\n").encode()


class PageStreamTests(unittest.TestCase):
    def test_title_arrives_before_first_drawing_section(self):
        titles, previews = [], []
        stream = PageStream(previews.append, titles.append)
        stream.feed(event('{"name":"Field note'))
        self.assertEqual(titles, [])
        stream.feed(event('book",'))
        self.assertEqual(titles, ["Field notebook"])
        self.assertEqual(previews, [])
        stream.feed(event('"sections":["g.clear(\\"red\\")"]'))
        self.assertEqual(len(previews), 1)
        self.assertEqual(len(titles), 1)

    def test_arbitrary_fragment_boundaries_and_escaped_strings(self):
        previews = []
        stream = PageStream(previews.append)
        first = """g.text(4,4,'é ["sections"]',14,'red');"""
        head = '{"name":"sections","browser":false,"toolbarHeight":80,"sections":[' + json.dumps(first, ensure_ascii=False)
        for byte in event(head):
            stream.feed(bytes([byte]))
        self.assertEqual(len(previews), 1)
        self.assertIn(first, previews[0])
        stream.feed(event(',"g.rect(0,0,3,3,\\"red\\");"],"input":""}'))
        stream.feed(b"data: [DONE]\n\n")
        self.assertIn("g.rect", stream.finish().script)

    def test_incomplete_stream_never_commits(self):
        for ending in (b"", b"data: [DONE]\n\n"):
            stream = PageStream(lambda _: None)
            stream.feed(event('{"sections":["g.clear(\\"red\\")"') + ending)
            with self.assertRaises(ValueError):
                stream.finish()

    def test_blank_section_between_valid_draws_is_a_noop(self):
        stream = PageStream(lambda _: None)
        page = dict(name="Gallery", browser=False, toolbarHeight=80,
                    sections=["g.clear('white')", "", "g.text(2,2,'Gallery')"], input="")
        stream.feed(event(json.dumps(page)) + b"data: [DONE]\n\n")
        self.assertIn("Gallery", stream.finish().script)

    def test_invalid_page_files(self):
        root = asdict(PagedProject())
        for features in ([], {"bad/id": asdict(DrawingProject())}, {"sub": root},
                         {"sub": {"version": 2, "name": "empty", "script": ""}}):
            with self.subTest(features=features), self.assertRaises(ValueError):
                Project.parse({**root, "features": features})
