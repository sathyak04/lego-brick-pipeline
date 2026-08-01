"""
Shared hollow shell → bond-pack → finish_shell_surface pipeline.

Used by demo_sphere (locked baseline) and demo_suite (sphere + bunny + teapot).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase4"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import STUD  # noqa: E402
from export_io import Brick  # noqa: E402
from greedy import consolidate_voxels, count_by_part  # noqa: E402
from connectivity import (  # noqa: E402
    ConnectivityReport,
    ClutchStrengthReport,
    check_connectivity,
    classify_weak_edges,
    clutch_strength,
)
from scaffold import (  # noqa: E402
    interior_voxels,
    shell_plus_scaffold,
    thicken_shell_inward,
)
from plate_bridge import finish_shell_surface  # noqa: E402
from voxelize import Voxel, voxelize_solid  # noqa: E402

PASS_SECTIONS = 1
PASS_COLLISIONS = 0
SHELL_THICKEN_LAYERS = 1


@dataclass
class HollowResult:
    name: str
    bricks: list[Brick]
    stats: dict
    report: ConnectivityReport
    strength: ClutchStrengthReport
    weak_diag: dict[str, int]
    shell_parts: int
    solid_count: int
    shell_count: int
    interior_count: int
    part_mix: dict[str, int]

    @property
    def ok(self) -> bool:
        return (
            self.report.section_count == PASS_SECTIONS
            and self.stats.get("collisions", 1) == PASS_COLLISIONS
        )

    @property
    def hollow_pct(self) -> float:
        return 100.0 * self.interior_count / max(self.solid_count, 1)


def fit_mesh(mesh, max_studs: float) -> None:
    """Scale longest axis to max_studs, ground on Y, center XZ."""
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))


def build_hollow_from_solid(
    solid: list[Voxel],
    *,
    name: str,
    shell_color: int = 15,
    tile_color: int = 15,
    plate_color: int = 72,
    thicken_layers: int = SHELL_THICKEN_LAYERS,
    verbose: bool = True,
) -> HollowResult:
    """Hollow shell + bond pack + finish_shell_surface on an already-voxelized solid."""
    if verbose:
        print(f"  solid={len(solid)}")
        print("Hollow shell + merge...")
    shell, interior, _sc, _ = shell_plus_scaffold(
        solid, stride=99, floor_every=0, belt_every=0, pin_columns=False
    )
    if thicken_layers > 0:
        before_n = len(shell)
        shell = thicken_shell_inward(solid, shell, layers=thicken_layers)
        interior = interior_voxels(solid, shell)
        if verbose:
            print(
                f"  early hollow thicken +{len(shell) - before_n} "
                f"(layers={thicken_layers})"
            )
    if verbose:
        print(
            f"  shell={len(shell)} cavities={len(interior)} "
            f"({100.0 * len(interior) / max(len(solid), 1):.0f}% hollow)"
        )
    placements = consolidate_voxels(shell, color=shell_color, stagger=True, bond=True)
    shell_part_count = len(placements)
    if verbose:
        print(f"  shell parts={shell_part_count} {count_by_part(placements)}")
        print("Connect shell (under-plates, staples, exterior tiles)...")

    solid_cells = {(v.ix, v.iy, v.iz) for v in solid}
    bricks, stats = finish_shell_surface(
        placements,
        shell_color=shell_color,
        tile_color=tile_color,
        plate_color=plate_color,
        solid=solid_cells,
    )
    report = check_connectivity(bricks)
    strength = clutch_strength(bricks, report)
    weak_diag = classify_weak_edges(
        bricks,
        report=report,
        strength=strength,
        shell_count=shell_part_count,
    )
    mix: dict[str, int] = {}
    for b in bricks:
        mix[b.part_id] = mix.get(b.part_id, 0) + 1

    if verbose:
        print(
            f"  under_plates={stats['under_plates']} "
            f"cavity_plates={stats.get('cavity_plates', 0)} "
            f"staples={stats.get('staples', 0)} tiles={stats['tiles']} "
            f"uncovered_studs={stats['uncovered_studs']} "
            f"collisions={stats['collisions']}"
        )
        print(
            f"  sections: {stats['sections_before']} -> "
            f"{stats['sections_after_under']} (after under) -> "
            f"{stats['sections_final']} (final)"
        )

    return HollowResult(
        name=name,
        bricks=bricks,
        stats=stats,
        report=report,
        strength=strength,
        weak_diag=weak_diag,
        shell_parts=shell_part_count,
        solid_count=len(solid),
        shell_count=len(shell),
        interior_count=len(interior),
        part_mix=mix,
    )


def build_hollow_from_mesh(
    mesh,
    *,
    name: str,
    max_studs: float,
    **kwargs,
) -> HollowResult:
    fit_mesh(mesh, max_studs)
    if kwargs.pop("verbose", True):
        print(f"Voxelizing {name} (max~{max_studs:.0f} studs)...")
    solid = voxelize_solid(mesh, use_raycast=True)
    return build_hollow_from_solid(solid, name=name, verbose=True, **kwargs)
