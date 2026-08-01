"""Phase 5 — part-count bloat audit unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bloat import check_bloat  # noqa: E402
from export_io import Brick  # noqa: E402


class TestBloat(unittest.TestCase):
    def test_single_brick_has_no_bloat(self) -> None:
        r = check_bloat([Brick("3004.dat", 15, 0.0, -24.0, 0.0)])
        self.assertEqual(r.merge_pairs, [])
        self.assertTrue(r.lean)

    def test_two_1x2_end_to_end_merge_into_1x4(self) -> None:
        # 1x2 spans 2 studs: x -20..20, then 20..60
        a = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        b = Brick("3004.dat", 15, 40.0, -24.0, 0.0)
        r = check_bloat([a, b])
        self.assertEqual(len(r.merge_pairs), 1)
        self.assertFalse(r.lean)
        self.assertEqual(r.merge_pairs[0].replacement, "3010.dat")

    def test_two_1x1_merge_into_1x2(self) -> None:
        a = Brick("3005.dat", 15, 0.0, -24.0, 0.0)
        b = Brick("3005.dat", 15, 20.0, -24.0, 0.0)
        r = check_bloat([a, b])
        self.assertEqual(len(r.merge_pairs), 1)
        self.assertEqual(r.wasted_parts, 1)

    def test_different_colors_stay_split(self) -> None:
        a = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        b = Brick("3004.dat", 4, 40.0, -24.0, 0.0)
        r = check_bloat([a, b])
        self.assertEqual(r.merge_pairs, [])

    def test_different_layers_stay_split(self) -> None:
        a = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        b = Brick("3004.dat", 15, 40.0, -48.0, 0.0)
        r = check_bloat([a, b])
        self.assertEqual(r.merge_pairs, [])

    def test_gap_between_bricks_stays_split(self) -> None:
        a = Brick("3004.dat", 15, 0.0, -24.0, 0.0)
        b = Brick("3004.dat", 15, 80.0, -24.0, 0.0)
        r = check_bloat([a, b])
        self.assertEqual(r.merge_pairs, [])

    def test_brick_and_plate_never_merge(self) -> None:
        a = Brick("3004.dat", 15, 0.0, -24.0, 0.0)  # brick 1x2
        b = Brick("3023.dat", 15, 40.0, -24.0, 0.0)  # plate 1x2
        r = check_bloat([a, b])
        self.assertEqual(r.merge_pairs, [])

    def test_each_brick_used_in_at_most_one_merge(self) -> None:
        # Three 1x2 in a row: only one pair may be claimed
        row = [Brick("3004.dat", 15, 40.0 * i, -24.0, 0.0) for i in range(3)]
        r = check_bloat(row)
        self.assertEqual(len(r.merge_pairs), 1)

    def test_no_catalog_part_means_no_merge(self) -> None:
        # 1x8 + 1x8 would need a 1x16 — not in the catalog
        a = Brick("3008.dat", 15, 0.0, -24.0, 0.0)
        b = Brick("3008.dat", 15, 160.0, -24.0, 0.0)
        r = check_bloat([a, b])
        self.assertEqual(r.merge_pairs, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
