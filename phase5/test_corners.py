"""Corner part catalog / stud mask checks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase2"))

from catalog import get_part, packing_templates  # noqa: E402
from connections import local_stud_xz  # noqa: E402


def test_corner_parts_in_catalog() -> None:
    brick = get_part("2357.dat")
    plate = get_part("2420.dat")
    assert brick.kind == "brick" and plate.kind == "plate"
    assert brick.width == plate.width == 2
    assert brick.depth == plate.depth == 2
    assert not brick.is_rectangular()
    assert not plate.is_rectangular()
    assert brick.occupied == ((0, 0), (1, 0), (0, 1))
    assert len(local_stud_xz(brick)) == 3
    assert len(local_stud_xz(plate)) == 3


def test_corners_excluded_from_rect_packing() -> None:
    ids = {t.part_id for t in packing_templates("brick")}
    assert "2357.dat" not in ids
    ids_p = {t.part_id for t in packing_templates("plate")}
    assert "2420.dat" not in ids_p
    assert "3001.dat" in ids
    assert "3023.dat" in ids_p
