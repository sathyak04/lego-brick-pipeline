"""
Unit tests: enclosed-cavity fill must NOT create overhang pillars.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from voxelize import Voxel  # noqa: E402
from connect_fix import (  # noqa: E402
    _as_set,
    build_connected_structure,
    fill_enclosed_cavities,
)


def _cantilever_t() -> set[tuple[int, int, int]]:
    """
    Cantilever T in voxel space:

         #####   <- head (iy=3), overhangs in ±X
           #
           #     <- neck
         #####   <- base (iy=0)

    Air under the head overhang (iy=1,2 at |x|>=1) is outside-reachable
    and must stay empty after fill_enclosed_cavities.
    """
    cells: set[tuple[int, int, int]] = set()
    # Base
    for x in range(-2, 3):
        cells.add((x, 0, 0))
    # Neck (center column)
    cells.add((0, 1, 0))
    cells.add((0, 2, 0))
    # Head bar
    for x in range(-2, 3):
        cells.add((x, 3, 0))
    return cells


class TestEnclosedCavities(unittest.TestCase):
    def test_cantilever_does_not_fill_overhang(self) -> None:
        solid = _cantilever_t()
        filled = fill_enclosed_cavities(solid)

        # Overhang air under head ends must remain empty
        for x in (-2, -1, 1, 2):
            for iy in (1, 2):
                self.assertNotIn(
                    (x, iy, 0),
                    filled,
                    f"pillar under overhang at {(x, iy, 0)}",
                )

        # Original solid preserved
        self.assertTrue(solid <= filled)

    def test_enclosed_box_cavity_is_filled(self) -> None:
        # 3x3x3 shell with hollow center
        cells: set[tuple[int, int, int]] = set()
        for x in range(3):
            for y in range(3):
                for z in range(3):
                    if x in (0, 2) or y in (0, 2) or z in (0, 2):
                        cells.add((x, y, z))
        # Center (1,1,1) empty and enclosed
        self.assertNotIn((1, 1, 1), cells)
        filled = fill_enclosed_cavities(cells)
        self.assertIn((1, 1, 1), filled)

    def test_structure_adds_no_overhang_cells(self) -> None:
        solid = [Voxel(ix, iy, iz) for ix, iy, iz in sorted(_cantilever_t())]
        report = build_connected_structure(solid, color=14, max_dilate=0)
        used = _as_set(report.voxels)
        for x in (-2, -1, 1, 2):
            for iy in (1, 2):
                self.assertNotIn(
                    (x, iy, 0),
                    used,
                    f"structure pass created pillar at {(x, iy, 0)}",
                )

    def test_no_ground_to_head_column_fill(self) -> None:
        """Classic bug: filling min→max iy under overhang. Must not happen."""
        solid = _cantilever_t()
        filled = fill_enclosed_cavities(solid)
        # Column x=2 has base iy=0 and head iy=3 — air at 1,2 must stay empty
        self.assertIn((2, 0, 0), filled)
        self.assertIn((2, 3, 0), filled)
        self.assertNotIn((2, 1, 0), filled)
        self.assertNotIn((2, 2, 0), filled)


if __name__ == "__main__":
    unittest.main()
