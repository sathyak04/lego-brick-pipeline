"""Phase 5 — structural interlocking / shear-plane unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_io import Brick  # noqa: E402
from interlock import check_interlock  # noqa: E402


class TestInterlock(unittest.TestCase):
    def test_single_brick_has_nothing_to_shear(self) -> None:
        r = check_interlock([Brick("3004.dat", 15, 0.0, -24.0, 0.0)])
        self.assertEqual(r.aligned_edges, 0)
        self.assertEqual(r.staggered_edges, 0)
        self.assertEqual(r.fragile_ids, [])
        self.assertTrue(r.interlocked)

    def test_aligned_stack_is_a_shear_column(self) -> None:
        # Identical footprints stacked straight up — a vertical shear plane
        low = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        high = Brick("3004.dat", 15, 0.0, -48.0, 0.0)
        r = check_interlock([low, high])
        self.assertEqual(r.aligned_edges, 1)
        self.assertEqual(r.staggered_edges, 0)
        self.assertEqual(r.fragile_ids, [0, 1])
        self.assertFalse(r.interlocked)

    def test_offset_stack_is_staggered(self) -> None:
        # Half-brick offset: seams no longer line up (brick-wall bond)
        low = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        high = Brick("3004.dat", 15, 20.0, -48.0, 0.0)
        r = check_interlock([low, high])
        self.assertEqual(r.staggered_edges, 1)
        self.assertEqual(r.aligned_edges, 0)
        self.assertEqual(r.fragile_ids, [])
        self.assertTrue(r.interlocked)

    def test_lintel_across_two_pillars_interlocks(self) -> None:
        left = Brick("3005.dat", 15, 0.0, -24.0, 0.0)
        right = Brick("3005.dat", 15, 40.0, -24.0, 0.0)
        lintel = Brick("3010.dat", 15, 20.0, -48.0, 0.0)  # 1x4 spans both
        r = check_interlock([left, right, lintel])
        self.assertEqual(r.staggered_edges, 2)
        self.assertTrue(r.interlocked)

    def test_one_cross_connection_saves_a_column(self) -> None:
        # Aligned pair, but the top brick also spans onto a neighbour column
        low = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        neighbour = Brick("3004.dat", 15, 40.0, -24.0, 0.0)
        spanning = Brick("3010.dat", 15, 20.0, -48.0, 0.0)
        r = check_interlock([low, neighbour, spanning])
        self.assertEqual(r.fragile_ids, [])

    def test_stagger_ratio_reported(self) -> None:
        low = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        aligned = Brick("3004.dat", 15, 0.0, -48.0, 0.0)
        r = check_interlock([low, aligned])
        self.assertEqual(r.stagger_ratio, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
