import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from vibe_cluster_counter import count_items


class TestCountItems(unittest.TestCase):
    def test_normal_list(self):
        self.assertEqual(count_items([1, 2, 3]), 3)

    def test_empty_list(self):
        self.assertEqual(count_items([]), 0)

    def test_returns_type(self):
        self.assertIsInstance(count_items([1]), int)


if __name__ == '__main__':
    unittest.main()
