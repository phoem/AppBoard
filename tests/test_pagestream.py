import json
import unittest

from appboard.pagestream import PageStream
from appboard.collectionview import is_collection_request
from appboard.native import Drawing
from appboard.sequence import sequence_candidate, sequence_schema, sequence_script
from appboard.project import DrawingProject, PagedProject, Project
from dataclasses import asdict


def event(text):
    payload = {"choices": [{"delta": {"content": text}}]}
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\r\n\r\n").encode()


class PageStreamTests(unittest.TestCase):
    def test_ordered_edits_stream_to_portable_source_and_keep_duplicates(self):
        spec = dict(key="takes", separator=" / ", append=[
            {"label": 'Cue "A}"', "value": "A"}, {"label": "Cue B", "value": "B"}],
            remove_last="Rewind", remove_first="Play", clear="Start over")
        previews = []
        stream = PageStream(previews.append, allow_sequence=True)
        # A provider may reorder fields, split an escape or deliver one byte at a time.
        prefix = '{"layout":' + json.dumps(spec) + ',"name":"Practice"'
        for char in prefix:
            stream.feed(event(char))
        self.assertEqual(len(previews), 1)
        stream.feed(event('}') + b"data: [DONE]\n\n")
        saved = Project.parse(asdict(stream.finish()))
        self.assertEqual(saved.script, previews[0])
        drawing = Drawing(saved.script)
        frame = drawing.frame(400, 270, data={"elsewhere": "preserved"})
        for label, expected in [('Play', []), ('Cue "A}"', ["A"]), ("Cue B", ["A", "B"]),
                                ('Cue "A}"', ["A", "B", "A"]), ("Rewind", ["A", "B"]),
                                ("Play", ["B"]), ("Start over", [])]:
            button = next(n for n in frame["nodes"] if n.get("value") == label)
            frame = drawing.frame(400, 270, {"type": "down", "x": button["x"], "y": button["y"]}, data=frame["data"])
            self.assertEqual(frame["data"], {"elsewhere": "preserved", "takes": expected})
            self.assertEqual(frame["nodes"][-1]["value"], " / ".join(expected))
        conflict = drawing.frame(400, 270, data={"takes": 12})
        self.assertEqual(conflict["data"], {"takes": 12})

    def test_ordered_edits_keep_custom_code_available(self):
        context = {"fromPage": "Home", "request": "Add samples to a list and drag to rearrange them"}
        self.assertTrue(sequence_candidate(context))
        self.assertFalse(sequence_candidate({**context, "currentPage": {}}))
        stream = PageStream(lambda _: None, allow_sequence=True, shared_scope=True)
        page = dict(name="Plot", layout=dict(sections=["const offset=12;", "g.circle(offset,10,4,'red');"],
                    input="function(e) { g.data.last = e.type; };", browser=False, toolbarHeight=80))
        stream.feed(event(json.dumps(page)) + b"data: [DONE]\n\n")
        result = Drawing(stream.finish().script).frame(200, 80, {"type": "down"})
        self.assertEqual(result["nodes"][0]["color"], "red")
        self.assertEqual(result["data"], {"last": "down"})

    def test_malformed_sequence_descriptions_are_rejected(self):
        valid = dict(key="samples", separator=", ", append=[], remove_last="Undo", remove_first="", clear="")
        for bad in ({"key": "__proto__"}, {"append": [{"label": "A", "value": []}]},
                    {"remove_last": ""}, {"clear": True}, {"unknown": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sequence_script("List", {**valid, **bad})

    def test_explicit_delimiters_preserve_whitespace_and_freeform_schema(self):
        for brief, expected in [("Show entries separated by ' | '.", " | "),
                                ('Display them joined with "".', "")]:
            with self.subTest(brief=brief):
                self.assertEqual(sequence_schema(brief)["properties"]["separator"]["enum"], [expected])
        self.assertNotIn("enum", sequence_schema("Use a suitable separator")["properties"]["separator"])
        fields = sequence_schema("Serve removes the first entry. Take back removes only the last note. "
                                 "'Flush' clears the list.")["properties"]
        for op, label in [("remove_first", "Serve"), ("remove_last", "Take back"), ("clear", "Flush")]:
            self.assertEqual(fields[op]["enum"], [label])

    def test_only_plain_new_collection_briefs_use_the_collection_format(self):
        feature = {"fromPage": "Home", "request": "Browse collection: inventory from g.data.stock"}
        self.assertTrue(is_collection_request(feature))
        self.assertTrue(is_collection_request({**feature, "request": "Open my album."}))
        self.assertFalse(is_collection_request({**feature, "request": "View Gallery and edit captions"}))
        self.assertFalse(is_collection_request({**feature, "currentPage": {}}))
        self.assertFalse(is_collection_request({"request": "View Gallery"}))

    def test_collection_compiles_during_stream_and_reopens_with_bound_data(self):
        previews = []
        stream = PageStream(previews.append, collection_key="gallery")
        spec = dict(collection="photos", labelField="caption", imageField="png", emptyText='No "photos" yet')
        prefix = json.dumps({"name": "Gallery", **spec})[:-1]
        for char in prefix:
            stream.feed(event(char))
        self.assertEqual(len(previews), 1)
        self.assertEqual(Drawing(previews[0]).frame(200, 180)["nodes"][-1]["value"], spec["emptyText"])
        stream.feed(event('}') + b"data: [DONE]\n\n")
        page = stream.finish()
        source = Project.parse(asdict(page)).script
        self.assertEqual(source, previews[0])
        drawing = Drawing(source)
        png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1kAAAAASUVORK5CYII="
        data = {"photos": [{"caption": "Hillside", "png": png}, "Shoreline", "Sunset"]}
        first = drawing.frame(200, 152, data=data)["nodes"]
        self.assertEqual([n["value"] for n in first if n["kind"] == "text"], ["Gallery", "Hillside"])
        self.assertEqual([n["png"] for n in first if n["kind"] == "image"], [png])
        next_row = drawing.frame(200, 152, {"type": "wheel", "delta": -120}, data=data)
        self.assertEqual(next_row["nodes"][-1]["value"], "Shoreline")
        self.assertEqual(drawing.frame(200, 152)["nodes"][-1]["value"], spec["emptyText"])

    def test_provisional_prefix_paints_before_json_string_closes(self):
        partial, complete = [], []
        stream = PageStream(complete.append, partial=partial.append)
        section = "g.text(4,4,'Requested title');"
        stream.feed(event('{"name":"Test","sections":[' + json.dumps(section)[:-1]))
        self.assertIn(section, partial[0])
        self.assertFalse(complete)
        stream.feed(event('g.rect(2,2,8,8,\\"red\\");"],"browser":false,"toolbarHeight":80,"input":""}'))
        stream.feed(b"data: [DONE]\n\n")
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete[0], stream.finish().script)

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
