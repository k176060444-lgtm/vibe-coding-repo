"""Tests for vibe_cluster_grey.py — V1.21.29U cluster grey run."""

import os
import sys
import unittest

# Add scripts to path (same pattern as other tests in this repo)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from vibe_cluster_grey import grey_marker

VIBE_CLUSTER_GREY_OK = "VIBE_CLUSTER_GREY_OK"


class TestGreyMarker(unittest.TestCase):

    def test_returns_correct_value(self):
        self.assertEqual(grey_marker(), VIBE_CLUSTER_GREY_OK)

    def test_returns_string(self):
        self.assertIsInstance(grey_marker(), str)

    def test_idempotent(self):
        self.assertEqual(grey_marker(), grey_marker())


if __name__ == "__main__":
    unittest.main()
