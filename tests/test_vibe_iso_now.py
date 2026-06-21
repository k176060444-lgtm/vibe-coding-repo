import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from vibe_iso_now import utc_now_iso, utc_now_structured


class TestVibeIsoNow(unittest.TestCase):
    def test_utc_now_iso_format(self):
        result = utc_now_iso()
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_utc_now_structured_keys(self):
        d = utc_now_structured()
        self.assertEqual(set(d), {"iso", "unix", "date", "time"})

    def test_utc_now_structured_types(self):
        d = utc_now_structured()
        self.assertIsInstance(d["iso"], str)
        self.assertIsInstance(d["unix"], int)
        self.assertIsInstance(d["date"], str)
        self.assertIsInstance(d["time"], str)


if __name__ == "__main__":
    unittest.main()
