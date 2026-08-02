"""Phase 6 — merge_bloat / stagger_seams unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from actions import merge_bloat, stagger_seams  # noqa: E402
from bloat import check_bloat  # noqa: E402
from export_io import Brick  # noqa: E402
from interlock import check_interlock  # noqa: E402


class TestMergeBloat(unittest.TestCase):
    def test_merges_two_1x2_into_1x4(self) -> None:
        a = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        b = Brick("3004.dat", 15, 40.0, -24.0, 0.0)
        self.assertFalse(check_bloat([a, b]).lean)
        after, n = merge_bloat([a, b])
        self.assertEqual(n, 1)
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].part_id, "3010.dat")
        self.assertTrue(check_bloat(after).lean)


class TestStaggerSeams(unittest.TestCase):
    def test_shifts_aligned_column(self) -> None:
        low = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        high = Brick("3004.dat", 15, 0.0, -48.0, 0.0)
        before = check_interlock([low, high])
        self.assertFalse(before.interlocked)
        after, n = stagger_seams([low, high], max_shifts=2)
        self.assertGreater(n, 0)
        self.assertTrue(check_interlock(after).interlocked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
