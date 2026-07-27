"""
Bunny only — hollow+beams, plus a HALF CUT so you can see inside.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import STUD  # noqa: E402
from mesh import load_obj  # noqa: E402
from voxelize import Voxel, export_voxels_io, voxelize_solid  # noqa: E402
from greedy import consolidate_voxels, export_placements_io, Placement  # noqa: E402
from scaffold import shell_plus_scaffold  # noqa: E402


def fit(mesh, max_studs: float):
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))


def cut_voxels_half_x(voxels: list[Voxel]) -> list[Voxel]:
    """Keep only cells with ix <= midpoint (cut down the middle)."""
    if not voxels:
        return []
    mid = (min(v.ix for v in voxels) + max(v.ix for v in voxels)) // 2
    return [v for v in voxels if v.ix <= mid]


def cut_placements_half_x(placements: list[Placement]) -> list[Placement]:
    if not placements:
        return []
    # Placement covers [ix, ix+w); keep if any of it is on the kept half,
    # but for a clean cut keep only if the whole footprint is on the left.
    mid = (min(p.ix for p in placements) + max(p.ix + p.w - 1 for p in placements)) // 2
    return [p for p in placements if (p.ix + p.w - 1) <= mid]


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase4"
    out.mkdir(parents=True, exist_ok=True)

    # Wipe old bunny outputs so only the new set remains
    for p in out.glob("*"):
        if p.is_file():
            p.unlink()

    bunny = load_obj(root / "assets" / "meshes" / "bunny.obj")
    fit(bunny, 28.0)

    print("voxelizing bunny...")
    solid = voxelize_solid(bunny, use_raycast=True)
    _shell, _interior, _scaffold, hollow = shell_plus_scaffold(
        solid,
        stride=2,
        floor_every=1,
        belt_every=1,
        pin_columns=False,
    )
    merged = consolidate_voxels(hollow, color=15, stagger=True)

    half_1x1 = cut_voxels_half_x(hollow)
    half_merged = cut_placements_half_x(merged)

    export_voxels_io(
        hollow,
        out / "1_full_hollow_beams.io",
        "Bunny full hollow+beams (1x1)",
        15,
    )
    export_placements_io(
        merged,
        out / "2_full_merged.io",
        "Bunny full hollow+beams MERGED",
    )
    export_voxels_io(
        half_1x1,
        out / "3_HALF_CUT_see_inside.io",
        "Bunny HALF CUT — look at beams inside",
        15,
    )
    export_placements_io(
        half_merged,
        out / "4_HALF_CUT_merged.io",
        "Bunny HALF CUT merged",
    )

    print()
    print("Open these (folder cleaned):")
    print(f"  1) {out / '1_full_hollow_beams.io'}   full model")
    print(f"  2) {out / '2_full_merged.io'}          full merged")
    print(f"  3) {out / '3_HALF_CUT_see_inside.io'}  << open this to see beams")
    print(f"  4) {out / '4_HALF_CUT_merged.io'}      half cut, merged bricks")
    print()
    print("Stability/gravity (pieces that would fall) = Phase 5 — not fixed yet.")


if __name__ == "__main__":
    main()
