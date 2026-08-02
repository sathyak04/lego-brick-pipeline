"""Phase 6 — support_blocked (experimental) + hill-climb unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from actions import merge_bloat, support_blocked_pieces  # noqa: E402
from build_order import check_build_order  # noqa: E402
from connectivity import check_connectivity  # noqa: E402
from export_io import Brick  # noqa: E402
from loop import improve_release  # noqa: E402
from state import evaluate  # noqa: E402


def _cavity_plate_fixture() -> list[Brick]:
    """1 clutch section, but a floating cavity plate is mid-air for build order."""
    a = Brick("3005.dat", 15, 0.0, -24.0, 0.0)
    b = Brick("3005.dat", 15, 0.0, -48.0, 0.0)
    c = Brick("3004.dat", 15, 10.0, -72.0, 0.0)
    plate = Brick("3024.dat", 72, 20.0, -48.0, 0.0)
    return [a, b, c, plate]


class TestSupportBlockedExperimental(unittest.TestCase):
    """Column supports stay testable but are not part of the release agent."""

    def test_fixture_is_hard_ok_but_not_buildable(self) -> None:
        bricks = _cavity_plate_fixture()
        self.assertEqual(check_connectivity(bricks).section_count, 1)
        self.assertFalse(check_build_order(bricks).buildable)

    def test_experimental_column_still_works(self) -> None:
        before = _cavity_plate_fixture()
        after, n = support_blocked_pieces(before, max_targets=2)
        self.assertGreater(n, 0)
        self.assertTrue(check_build_order(after).buildable)


class TestHillClimb(unittest.TestCase):
    def test_loop_does_not_register_support_columns(self) -> None:
        from actions import ACTIONS

        self.assertNotIn("support_blocked_pieces", ACTIONS)

    def test_loop_does_not_stuff_columns_for_mid_air(self) -> None:
        start = evaluate(_cavity_plate_fixture(), interior_count=1, solid_count=2)
        result = improve_release(start, max_rounds=5)
        # May improve tip/clutch/etc., but must not grow a stud forest.
        self.assertLessEqual(len(result.final.bricks), len(start.bricks) + 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
