"""Unit tests: exterior tile cover + underside plate strips + catalog packing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase4"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import PLATE_H, get_part, packing_templates  # noqa: E402
from greedy import IDENTITY, Placement, consolidate_layer, placements_to_bricks  # noqa: E402
from connectivity import check_connectivity  # noqa: E402
from plate_bridge import (  # noqa: E402
    bridge_with_plates,
    cover_exterior_with_tiles,
    finish_shell_surface,
    _make_part,
    _brick_top_y,
)
from brick_collision import collides_any, count_collisions  # noqa: E402
from voxelize import Voxel  # noqa: E402
from greedy import consolidate_voxels  # noqa: E402


def test_catalog_packing_templates_largest_first() -> None:
    bricks = packing_templates("brick")
    assert bricks[0].area >= bricks[-1].area
    assert any(t.area >= 8 for t in bricks)  # e.g. 2x4 or 1x8
    tiles = packing_templates("tile")
    assert any(t.area >= 6 for t in tiles)  # 1x6+ or 2x4+
    assert get_part("3009.dat").width == 6
    assert get_part("4162.dat").kind == "tile"


def test_greedy_uses_long_brick_on_run() -> None:
    """An 8-stud-long 1-wide row should place a 1x6 or 1x8 brick."""
    cells = {(x, 0) for x in range(8)}
    placed = consolidate_layer(cells, iy=0, color=15, stagger=False)
    areas = [p.w * p.d for p in placed]
    assert max(areas) >= 6
    assert any(p.part_id in ("3009.dat", "3008.dat") for p in placed)


def test_tile_cover_uses_long_strip() -> None:
    """A 6-stud exposed top run should place a 1x6 (or longer) tile."""
    placements = [
        Placement("3005.dat", 15, x, 0, 0, 1, 1, IDENTITY) for x in range(6)
    ]
    shell = placements_to_bricks(placements)
    tiles, uncovered = cover_exterior_with_tiles(placements, shell, tile_color=15)
    assert uncovered == 0
    assert any(t.part_id in ("6636.dat", "4162.dat") for t in tiles)


def test_exterior_fully_tiled_zero_exposed_studs() -> None:
    placements = [
        Placement("3005.dat", 15, 0, 0, 0, 1, 1, IDENTITY),
        Placement("3005.dat", 15, 1, 0, 0, 1, 1, IDENTITY),
    ]
    shell = placements_to_bricks(placements)
    tiles, uncovered = cover_exterior_with_tiles(placements, shell, tile_color=15)
    assert uncovered == 0
    assert len(tiles) >= 1
    assert all(get_part(t.part_id).kind == "tile" for t in tiles)
    assert count_collisions(shell + tiles) == 0


def test_two_adjacent_join_via_finish() -> None:
    placements = [
        Placement("3005.dat", 15, 0, 0, 0, 1, 1, IDENTITY),
        Placement("3005.dat", 15, 1, 0, 0, 1, 1, IDENTITY),
    ]
    assert check_connectivity(placements_to_bricks(placements)).section_count == 2
    all_bricks, stats = finish_shell_surface(placements)
    assert stats["uncovered_studs"] == 0
    assert stats["collisions"] == 0
    assert stats["sections_final"] == 1


def test_reject_tile_colliding_with_brick_above() -> None:
    placements = [
        Placement("3005.dat", 15, 0, 0, 0, 1, 1, IDENTITY),
        Placement("3005.dat", 15, 1, 0, 0, 1, 1, IDENTITY),
        Placement("3005.dat", 15, 0, 1, 0, 1, 1, IDENTITY),
    ]
    illegal = _make_part(
        "3069b.dat", 71, 0, 0, 2, 1, IDENTITY, _brick_top_y(0) - PLATE_H
    )
    assert collides_any(illegal, placements_to_bricks(placements))
    all_bricks, stats = finish_shell_surface(placements)
    assert stats["collisions"] == 0
    assert count_collisions(all_bricks) == 0


def test_bridge_with_plates_compat() -> None:
    placements = [Placement("3004.dat", 15, 0, 0, 0, 2, 1, IDENTITY)]
    all_bricks, extras, sec_b, sec_a = bridge_with_plates(placements)
    assert sec_b == 1 and sec_a == 1
    assert count_collisions(all_bricks) == 0


def test_no_tiles_on_cavity_facing_tops() -> None:
    """Hollow column: floor top faces cavity — must stay studded; roof is tiled."""
    placements = [
        Placement("3005.dat", 15, 0, 0, 0, 1, 1, IDENTITY),  # floor
        Placement("3005.dat", 15, 0, 2, 0, 1, 1, IDENTITY),  # roof
    ]
    # Pre-hollow solid filled the middle (cavity after shell extract)
    solid = {(0, 0, 0), (0, 1, 0), (0, 2, 0)}
    shell = placements_to_bricks(placements)
    tiles, uncovered = cover_exterior_with_tiles(
        placements, shell, tile_color=15, solid=solid
    )
    assert uncovered == 0
    assert len(tiles) == 1
    assert tiles[0].y == _brick_top_y(2) - PLATE_H
    # Without solid, both tops would be tiled (regression guard)
    tiles_bad, _ = cover_exterior_with_tiles(placements, shell, tile_color=15)
    assert len(tiles_bad) == 2


def test_cavity_plate_joins_same_layer() -> None:
    """Two adjacent cavity-facing bricks join via a plate on their tops."""
    placements = [
        Placement("3005.dat", 15, 0, 0, 0, 1, 1, IDENTITY),
        Placement("3005.dat", 15, 1, 0, 0, 1, 1, IDENTITY),
    ]
    # Solid above = cavity; no exterior above
    solid = {(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)}
    assert check_connectivity(placements_to_bricks(placements)).section_count == 2
    from plate_bridge import bridge_cavity_with_plates

    plates, before, after = bridge_cavity_with_plates(
        placements, [], solid, plate_color=72
    )
    assert before == 2
    assert after == 1
    assert len(plates) >= 1
    assert count_collisions(placements_to_bricks(placements) + plates) == 0


def test_staple_joins_vertical_gap() -> None:
    """1-cell solid gap between two stacked columns joins via a staple."""
    placements = [
        Placement("3005.dat", 15, 0, 0, 0, 1, 1, IDENTITY),
        Placement("3005.dat", 15, 0, 2, 0, 1, 1, IDENTITY),
    ]
    solid = {(0, 0, 0), (0, 1, 0), (0, 2, 0)}
    assert check_connectivity(placements_to_bricks(placements)).section_count == 2
    from plate_bridge import staple_vertical_gaps

    staples, _vox, before, after = staple_vertical_gaps(
        placements, [], solid, staple_color=71, max_gap=3
    )
    assert before == 2
    assert after == 1
    assert len(staples) == 1
    assert count_collisions(placements_to_bricks(placements) + staples) == 0


def test_finish_hollow_column_connected() -> None:
    """Full pipeline on a hollow column → 1 section, exterior roof tiled only."""
    placements = [
        Placement("3005.dat", 15, 0, 0, 0, 1, 1, IDENTITY),
        Placement("3005.dat", 15, 0, 2, 0, 1, 1, IDENTITY),
    ]
    solid = {(0, 0, 0), (0, 1, 0), (0, 2, 0)}
    all_bricks, stats = finish_shell_surface(placements, solid=solid)
    assert stats["sections_final"] == 1
    assert stats["collisions"] == 0
    assert stats["uncovered_studs"] == 0
    assert stats["staples"] >= 1
