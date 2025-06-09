import unittest
import os
import tempfile

from staticfg.builder import CFGBuilder

sample_code = """\
def sample_function1(x):
    sum = 0
    if x > 0:
        sum += x
        return 'Positive'
    elif x < 0:
        sum += x
        return 'Negative'
    else:
        return 'Zero'
"""

class TestDFGPaths(unittest.TestCase):
    def test_paths_generated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snippet = os.path.join(tmpdir, 'snippet.py')
            with open(snippet, 'w') as f:
                f.write(sample_code)
            cfg_name = os.path.join(tmpdir, 'cfg_python')
            CFGBuilder().build_from_file(cfg_name, snippet)
            out_path = cfg_name + '_dfg.txt'
            with open(out_path) as f:
                lines = [line.strip() for line in f if line.strip()]
        self.assertIn('Path 1: (x, 1) -> (x, 3) -> (x, 4)', lines)
        self.assertIn('Path 2: (x, 1) -> (x, 3) -> (x, 6) -> (x, 7)', lines)
        self.assertIn('Path 3: (x, 1) -> (x, 3) -> (x, 6)', lines)

if __name__ == '__main__':
    unittest.main()
