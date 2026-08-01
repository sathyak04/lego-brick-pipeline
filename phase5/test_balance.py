"""Phase 5 balance unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from balance import check_balance  # noqa: E402
from export_io import Brick  # noqa: E402


class TestBalance(unittest.TestCase):
    def test_centered_2x4_passes(self) -> None:
        # Single 2x4 on ground — CoM at center of footprint
        b = Brick("3001.dat", 4, 0.0, -24.0, 0.0)
        r = check_balance([b], min_margin_studs=0.5)
        self.assertFalse(r.tip_hazard)
        self.assertTrue(r.inside)

    def test_offset_heavy_tip(self) -> None:
        # Small base on ground + offset mass above it (not on ground).
        # Tower bottoms must sit above ground_y or they enlarge the footprint.
        base = Brick("3001.dat", 4, 0.0, -24.0, 0.0)
        tower = [
            Brick("3005.dat", 4, 200.0, -24.0 * (i + 2), 0.0)
            for i in range(10)
        ]
        r = check_balance([base] + tower, min_margin_studs=1.0)
        self.assertEqual(r.ground_parts, 1)
        self.assertTrue(r.tip_hazard)
        self.assertFalse(r.inside)


if __name__ == "__main__":
    unittest.main(verbosity=2)
