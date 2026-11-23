import tempfile
import unittest
from pathlib import Path

import quickjs

from appboard.native import Drawing, checked_frame
from appboard.project import DrawingProject, Project


class NativeTests(unittest.TestCase):
    def test_versioned_files_round_trip(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "app.appboard"
            for p in (DrawingProject(), Project()):
                p.save(path)
                self.assertEqual(Project.load(path), p)
                self.assertIsInstance(Project.load(path), type(p))
            with self.assertRaises(ValueError):
                Project.parse({"version": 2, "name": "wrong", "html": "<p>Hello</p>"})

    def test_isolated_input_and_draw_operations(self):
        script = """
        let label = 'One';
        function input(e) { if (e.type === 'key') label = e.text; }
        function draw(g,w,h) {
          g.clear('white'); g.circle(20,20,5,'red'); g.text(10,10,label);
          g.path('M0 0 L4 0 L0 4 Z','blue'); g.line(0,0,w,h,'black'); g.animate();
        }
        """
        first, second = Drawing(script), Drawing(script)
        frame = first.frame(300, 180, {"type": "key", "text": "Two"})
        self.assertTrue(frame["animate"])
        self.assertEqual([n["kind"] for n in frame["nodes"]], ["rect", "rect", "text", "path", "path"])
        self.assertEqual(frame["nodes"][2]["value"], "Two")
        self.assertEqual(second.frame(50, 40)["nodes"][2]["value"], "One")

    def test_limits_and_missing_entry_point(self):
        with self.assertRaises(quickjs.JSException):
            Drawing("while(true) {}")
        for script in ("let count=1;", "function draw(g) {while(true) {}}",
                       "function draw(g) {for(let i=0;i<513;i++) g.rect(i,0,1,1,'red')}",
                       "function draw(g) {g.rect(0,0,NaN,10,'red')}",
                       "function draw(g) {g.image(0,0,8,8,'file:///test.png')}"):
            with self.subTest(script=script), self.assertRaises((ValueError, quickjs.JSException)):
                Drawing(script).frame(40, 40)
        with self.assertRaises(ValueError):
            checked_frame('{"nodes":[{"kind":"unknown"}],"commands":[],"animate":false}')

    def test_drawn_controls_share_hit_regions_and_handle_focused_text(self):
        drawing = Drawing("""
            function draw(g) {
              if(g.button(0,0,80,30,'Add')) g.data.added = (g.data.added || 0) + 1;
              const entry = g.textField(0,40,180,30,'term','Search');
              g.textField(0,40,180,30,'term','Search');
              if(entry.submitted) g.browser.navigate(entry.value);
              g.textField(0,80,180,30,'other','Other');
            }
        """)
        data = {}
        def frame(event=None):
            nonlocal data
            result = drawing.frame(300, 150, event, data=data)
            data = result["data"]
            return result
        def press(y):
            return frame({"type": "down", "x": 8, "y": y})
        def key(code, text="", modifiers=0):
            return frame({"type": "key", "key": code, "text": text, "modifiers": modifiers})
        self.assertIn("Search", [n.get("value") for n in frame()["nodes"]])
        press(10)
        frame({"type": "up", "x": 8, "y": 10})
        frame()
        self.assertEqual(data, {"added": 1})
        press(48)
        key(65, "a")
        key(66, "b")
        key(16777219)
        self.assertEqual(data["term"], "a")
        key(65, "a", 0x04000000)
        key(67, "c")
        self.assertEqual(key(16777220)["commands"], [["navigate", "c"]])
        self.assertEqual(frame()["commands"], [])
        press(88)
        key(68, "d")
        self.assertEqual((data["term"], data["other"]), ("c", "d"))
        press(140)
        key(69, "e")
        self.assertEqual(data["other"], "d")
