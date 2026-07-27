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
        # Wide base + heavy brick far outside — should tip
        base = Brick("3001.dat", 4, 0.0, -24.0, 0.0)
        # Another 2x4 shifted far on X at same height (floating mass) — use stacked height
        # Put a tall tower of 1x1s offset so CoM leaves footprint
        tower = [
            Brick("3005.dat", 4, 80.0, -24.0 * (i + 1), 0.0)
            for i in range(6)
        ]
        r = check_balance([base] + tower, min_margin_studs=1.0)
        self.assertTrue(r.tip_hazard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
