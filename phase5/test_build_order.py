"""Phase 5 Step 3 — build-order / instruction feasibility unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_order import check_build_order  # noqa: E402
from export_io import Brick  # noqa: E402
from overhang import check_overhangs  # noqa: E402


class TestBuildOrder(unittest.TestCase):
    def test_single_brick_buildable(self) -> None:
        b = Brick("3001.dat", 4, 0.0, -24.0, 0.0)
        r = check_build_order([b])
        self.assertTrue(r.buildable)
        self.assertEqual(r.order, [0])
        self.assertEqual(r.blocked_ids, [])

    def test_stack_buildable_bottom_first(self) -> None:
        # Ground 1x1, then one on top
        bottom = Brick("3005.dat", 4, 0.0, -24.0, 0.0)
        top = Brick("3005.dat", 4, 0.0, -48.0, 0.0)
        r = check_build_order([bottom, top])
        self.assertTrue(r.buildable)
        self.assertEqual(r.order, [0, 1])

    def test_arch_buildable(self) -> None:
        # Two ground pillars + lintel spanning them
        left = Brick("3005.dat", 4, 0.0, -24.0, 0.0)
        right = Brick("3005.dat", 4, 40.0, -24.0, 0.0)
        lintel = Brick("3004.dat", 4, 20.0, -48.0, 0.0)  # 1x2 across
        r = check_build_order([left, right, lintel])
        self.assertTrue(r.buildable)
        self.assertEqual(set(r.order[:2]), {0, 1})
        self.assertEqual(r.order[-1], 2)

    def test_side_cantilever_blocked(self) -> None:
        # Stack + same-layer neighbor with nothing under it.
        # Overhang may still call it "supported" via lateral touch;
        # build order must block mid-air placement.
        base = Brick("3005.dat", 4, 0.0, -24.0, 0.0)
        upper = Brick("3005.dat", 4, 0.0, -48.0, 0.0)
        float_side = Brick("3005.dat", 4, 20.0, -48.0, 0.0)
        bricks = [base, upper, float_side]
        overhang = check_overhangs(bricks)
        self.assertEqual(overhang.unsupported_ids, [])  # lateral path
        r = check_build_order(bricks)
        self.assertFalse(r.buildable)
        self.assertIn(2, r.blocked_ids)
        self.assertEqual(r.order, [0, 1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
