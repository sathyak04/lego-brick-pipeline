"""Phase 6 — support_blocked_pieces + hill-climb unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from actions import support_blocked_pieces  # noqa: E402
from build_order import check_build_order  # noqa: E402
from connectivity import check_connectivity  # noqa: E402
from export_io import Brick  # noqa: E402
from loop import improve_release  # noqa: E402
from state import evaluate  # noqa: E402


def _cavity_plate_fixture() -> list[Brick]:
    """1 clutch section, but a floating cavity plate is mid-air for build order.

    Stack A→B, then 1x2 C on B overhanging +X, with a 1x1 plate under the
    overhang stud. Plate clutches to C (same section) but sits above ground.
    """
    a = Brick("3005.dat", 15, 0.0, -24.0, 0.0)
    b = Brick("3005.dat", 15, 0.0, -48.0, 0.0)
    c = Brick("3004.dat", 15, 10.0, -72.0, 0.0)  # 1x2 spans x=0 and x=20
    plate = Brick("3024.dat", 72, 20.0, -48.0, 0.0)  # under overhang stud
    return [a, b, c, plate]


class TestSupportBlocked(unittest.TestCase):
    def test_fixture_is_hard_ok_but_not_buildable(self) -> None:
        bricks = _cavity_plate_fixture()
        self.assertEqual(check_connectivity(bricks).section_count, 1)
        self.assertFalse(check_build_order(bricks).buildable)

    def test_adds_column_under_cavity_plate(self) -> None:
        before = _cavity_plate_fixture()
        after, n = support_blocked_pieces(before, max_targets=2)
        self.assertGreater(n, 0)
        self.assertEqual(check_connectivity(after).section_count, 1)
        self.assertTrue(check_build_order(after).buildable)

    def test_noop_when_already_buildable(self) -> None:
        bricks = [
            Brick("3005.dat", 15, 0.0, -24.0, 0.0),
            Brick("3005.dat", 15, 0.0, -48.0, 0.0),
        ]
        after, n = support_blocked_pieces(bricks)
        self.assertEqual(n, 0)
        self.assertEqual(len(after), len(bricks))


class TestHillClimb(unittest.TestCase):
    def test_loop_raises_score_on_cavity_plate(self) -> None:
        start = evaluate(_cavity_plate_fixture(), interior_count=1, solid_count=2)
        self.assertTrue(start.hard_ok)
        self.assertFalse(start.release.release_ready)

        result = improve_release(start, max_rounds=5)
        self.assertGreater(result.accepted, 0)
        self.assertGreater(result.final.score, start.score)
        self.assertTrue(result.final.hard_ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
