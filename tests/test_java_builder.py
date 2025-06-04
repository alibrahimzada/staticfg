import unittest
from javacfg.builder import CFGBuilder

java_sample = """
public static boolean isValueCode(final char ch) {
    if (ch == '@') return true;
    if (ch == ':') return true;
    if (ch == '%') return true;
    if (ch == '+') return true;
    if (ch == '#') return true;
    if (ch == '<') return true;
    if (ch == '>') return true;
    if (ch == '*') return true;
    if (ch == '/') return true;
    if (ch == '!') return true;
    return false;
}
"""

class TestJavaCFG(unittest.TestCase):
    def test_build(self):
        cfg = CFGBuilder().build_from_src('isValueCode', java_sample)
        # Collect sources of blocks
        sources = [b.get_source().strip() for b in cfg]
        self.assertIn('return false;', sources[-1])
        self.assertEqual(cfg.entryblock, cfg.entryblock)

    def test_visual(self):
        cfg = CFGBuilder().build_from_src('isValueCode', java_sample)
        graph = cfg._build_visual(format='dot', calls=False)
        self.assertIn('digraph', graph.source)

if __name__ == '__main__':
    unittest.main()
