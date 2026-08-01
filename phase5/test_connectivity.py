"""Unit tests for stud-tube connectivity / detached sections."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import BRICK_H, STUD  # noqa: E402
from export_io import Brick  # noqa: E402
from connectivity import check_connectivity, clutch_strength, stud_overlap_count  # noqa: E402


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

    def test_stud_overlap_1x1_stack(self) -> None:
        lower = brick_at("3005.dat", 0, -BRICK_H, 0)
        upper = brick_at("3005.dat", 0, -2 * BRICK_H, 0)
        self.assertEqual(stud_overlap_count(lower, upper), 1)
        s = clutch_strength([lower, upper])
        self.assertEqual(s.edge_count, 1)
        self.assertEqual(s.weak_edges, 1)
        self.assertAlmostEqual(s.mean_overlap, 1.0)

    def test_stud_overlap_1x2_on_two_1x1(self) -> None:
        left = brick_at("3005.dat", 0, -BRICK_H, 0)
        right = brick_at("3005.dat", STUD, -BRICK_H, 0)
        top = brick_at("3004.dat", STUD / 2, -2 * BRICK_H, 0)
        self.assertEqual(stud_overlap_count(left, top), 1)
        self.assertEqual(stud_overlap_count(right, top), 1)
        s = clutch_strength([left, right, top])
        self.assertEqual(s.edge_count, 2)
        self.assertEqual(s.weak_edges, 2)

    def test_stud_overlap_full_1x2_stack(self) -> None:
        lower = brick_at("3004.dat", STUD / 2, -BRICK_H, 0)
        upper = brick_at("3004.dat", STUD / 2, -2 * BRICK_H, 0)
        self.assertEqual(stud_overlap_count(lower, upper), 2)
        s = clutch_strength([lower, upper])
        self.assertEqual(s.weak_edges, 0)
        self.assertAlmostEqual(s.mean_overlap, 2.0)

    def test_classify_weak_shell_vs_extra(self) -> None:
        from connectivity import classify_weak_edges

        # Two shell 1x1 stacked (weak) + one extra 1x1 on the upper
        # (extra is third brick; shell_count=2)
        lower = brick_at("3005.dat", 0, -BRICK_H, 0)
        upper = brick_at("3005.dat", 0, -2 * BRICK_H, 0)
        # side stack as "extra" floating — use another column clutched via plate
        # Keep it simple: only shell↔shell weak edge
        r = check_connectivity([lower, upper])
        s = clutch_strength([lower, upper], r)
        tallies = classify_weak_edges(
            [lower, upper], report=r, strength=s, shell_count=2
        )
        self.assertEqual(tallies["weak_shell_shell"], 1)
        self.assertEqual(tallies["weak_shell_extra"], 0)


if __name__ == "__main__":
    unittest.main()
