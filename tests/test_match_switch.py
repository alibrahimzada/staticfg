import unittest
from staticfg.builder import CFGBuilder
from javacfg.builder import CFGBuilder as JCFGBuilder

python_sample = """
def test_match_statement(value):
    match value:
        case 1:
            print('One')
        case 2 | 3:
            print('Two or Three')
        case _:
            print('Other')
    print('After match')
"""

java_sample = """
public static void testMatchStatement(int value) {
    switch (value) {
        case 1:
            System.out.println("One");
            break;
        case 2:
        case 3:
            System.out.println("Two or Three");
            break;
        default:
            System.out.println("Other");
            break;
    }
    System.out.println("After match");
}
"""

class TestMatchSwitch(unittest.TestCase):
    def test_python_match(self):
        cfg = CFGBuilder().build_from_src('test', python_sample)
        sources = [b.get_source().strip() for b in cfg]
        self.assertIn("print('After match')", sources[-1])

    def test_java_switch(self):
        cfg = JCFGBuilder().build_from_src('testMatchStatement', java_sample)
        sources = [b.get_source().strip() for b in cfg]
        self.assertIn('System.out.println("After match");', sources)

if __name__ == '__main__':
    unittest.main()
