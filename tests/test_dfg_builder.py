import unittest
import os
import tempfile
from staticfg.dfg_builder import DFGBuilder
from javacfg.dfg_builder import DFGBuilder as JDFGBuilder

sample_python = """
def foo(x):
    if x > 0:
        return "Positive"
    else:
        return "Non"
"""

sample_java = """
public static String foo(int x) {
    if (x > 0) {
        return "Positive";
    } else {
        return "Non";
    }
}
"""


class TestDFGBuilder(unittest.TestCase):
    def test_python_dfg(self):
        dfg = DFGBuilder().build_from_src("foo", sample_python)
        names = [n.name for n in dfg.nodes]
        self.assertIn("x", names)
        self.assertIn("x > 0", names)
        self.assertIn("'Positive'", names)
        graph = dfg._build_visual(format="dot")
        self.assertIn("digraph", graph.source)

    def test_python_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py") as tmp:
            tmp.write(sample_python)
            path = tmp.name
        dfg = DFGBuilder().build_from_file("foo", path)
        os.unlink(path)
        self.assertEqual(len(dfg.nodes), 4)

    def test_java_dfg(self):
        dfg = JDFGBuilder().build_from_src("foo", sample_java)
        names = [n.name for n in dfg.nodes]
        self.assertIn("x > 0", names)
        self.assertIn("return \"Positive\";", names)
        graph = dfg._build_visual(format="dot")
        self.assertIn("digraph", graph.source)


if __name__ == "__main__":
    unittest.main()
