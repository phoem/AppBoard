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
