import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from vibe_cluster_node_label import node_label


class TestNodeLabel(unittest.TestCase):
    def test_returns_correct_label(self):
        self.assertEqual(node_label('test'), 'node:test')

    def test_returns_string(self):
        self.assertIsInstance(node_label('test'), str)

    def test_empty_name(self):
        self.assertEqual(node_label(''), 'node:')


if __name__ == '__main__':
    unittest.main()
