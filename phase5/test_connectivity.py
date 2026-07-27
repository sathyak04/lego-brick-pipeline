"""Unit tests for stud-tube connectivity / detached sections."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import BRICK_H, STUD  # noqa: E402
from export_io import Brick  # noqa: E402
from connectivity import check_connectivity  # noqa: E402


def brick_at(part: str, x: float, y: float, z: float) -> Brick:
    return Brick(part_id=part, color=15, x=x, y=y, z=z)


class TestConnectivity(unittest.TestCase):
    def test_single_brick_one_section(self) -> None:
        r = check_connectivity([brick_at("3005.dat", 0, -BRICK_H, 0)])
        self.assertEqual(r.section_count, 1)
        self.assertEqual(len(r.edges), 0)

    def test_stacked_1x1_one_section(self) -> None:
        # Lower top at -24, upper bottom at -24 → clutch
        lower = brick_at("3005.dat", 0, -BRICK_H, 0)
        upper = brick_at("3005.dat", 0, -2 * BRICK_H, 0)
        r = check_connectivity([lower, upper])
        self.assertEqual(r.section_count, 1)
        self.assertEqual(len(r.edges), 1)

    def test_side_by_side_two_sections(self) -> None:
        # Adjacent same layer — NO clutch (Studio: 2 detached sections)
        a = brick_at("3005.dat", 0, -BRICK_H, 0)
        b = brick_at("3005.dat", STUD, -BRICK_H, 0)
        r = check_connectivity([a, b])
        self.assertEqual(r.section_count, 2)
        self.assertEqual(len(r.edges), 0)

    def test_staggered_bridge_one_section(self) -> None:
        # Two ground 1x1 with gap, 1x2 plate/brick on top linking both
        # Use 1x2 brick spanning both studs
        left = brick_at("3005.dat", 0, -BRICK_H, 0)
        right = brick_at("3005.dat", STUD, -BRICK_H, 0)
        # 3004 is 2x1: origin between studs → center at x=10
        top = brick_at("3004.dat", STUD / 2, -2 * BRICK_H, 0)
        r = check_connectivity([left, right, top])
        self.assertEqual(r.section_count, 1)
        self.assertEqual(len(r.edges), 2)

    def test_floating_island(self) -> None:
        ground = brick_at("3005.dat", 0, -BRICK_H, 0)
        # Floating stack far away — separate component
        a = brick_at("3005.dat", 200, -BRICK_H * 5, 0)
        b = brick_at("3005.dat", 200, -BRICK_H * 6, 0)
        r = check_connectivity([ground, a, b])
        self.assertEqual(r.section_count, 2)


if __name__ == "__main__":
    unittest.main()
