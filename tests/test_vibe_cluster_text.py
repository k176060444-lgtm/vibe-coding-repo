import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from vibe_cluster_text import normalize_text


class TestNormalizeText(unittest.TestCase):
    def test_normal_text(self):
        self.assertEqual(normalize_text('Hello'), 'hello')

    def test_with_spaces(self):
        self.assertEqual(normalize_text('  World  '), 'world')

    def test_mixed_case(self):
        self.assertEqual(normalize_text('FOO Bar'), 'foo bar')


if __name__ == '__main__':
    unittest.main()
