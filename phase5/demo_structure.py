"""
General clutch-structure demo (any mesh → connected .io, no overhang pillars).

Uses build_connected_structure: enclosed cavities only, crack-close,
staples + merge + cut repair. Never column air-fill.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase4"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import STUD  # noqa: E402
from export_io import export_bricks_to_io  # noqa: E402
from mesh import load_obj  # noqa: E402
from voxelize import voxelize_solid  # noqa: E402
from greedy import placements_to_bricks, count_by_part  # noqa: E402
from connect_fix import (  # noqa: E402
    _as_set,
    build_connected_structure,
    fill_enclosed_cavities,
)
from connectivity import check_connectivity, format_connectivity_report  # noqa: E402


def fit(mesh, max_studs: float) -> None:
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))


def overhang_air(solid: set[tuple[int, int, int]]) -> set[tuple[int, int, int]]:
    """Empty cells in bbox reachable from outside (overhang / exterior)."""
    if not solid:
        return set()
    filled = fill_enclosed_cavities(solid)
    ix0, ix1 = min(c[0] for c in solid), max(c[0] for c in solid)
    iy0, iy1 = min(c[1] for c in solid), max(c[1] for c in solid)
    iz0, iz1 = min(c[2] for c in solid), max(c[2] for c in solid)
    empty = {
        (x, y, z)
        for x in range(ix0, ix1 + 1)
        for y in range(iy0, iy1 + 1)
        for z in range(iz0, iz1 + 1)
        if (x, y, z) not in solid
    }
    cavities = filled - solid
    return empty - cavities


def count_illegal_overhang_fills(
    original: set[tuple[int, int, int]],
    used: set[tuple[int, int, int]],
) -> int:
    """
    Used cells in overhang air that are NOT face-adjacent to the original
    solid (violates keep_near / no deep pillar rule).
    """
    air = overhang_air(original)
    bad = 0
    for ix, iy, iz in used:
        if (ix, iy, iz) not in air:
            continue
        if not any(
            (ix + dx, iy + dy, iz + dz) in original for dx, dy, dz in (
                (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
            )
        ):
            bad += 1
    return bad


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase5"
    out.mkdir(parents=True, exist_ok=True)

    print("Voxelizing bunny (example mesh)...")
    bunny = load_obj(root / "assets" / "meshes" / "bunny.obj")
    fit(bunny, 28.0)
    solid = voxelize_solid(bunny, use_raycast=True)
    original = _as_set(solid)
    print(f"  solid voxels: {len(solid)}")

    print("build_connected_structure (model-agnostic, no pillars)...")
    report = build_connected_structure(solid, color=14, close_rounds=2, max_dilate=2)
    bricks = placements_to_bricks(report.placements)
    conn = check_connectivity(bricks)

    print(format_connectivity_report(conn, bricks))
    print(f"  structure: {report.verdict}")
    print(
        f"  voxels_added: {report.voxels_added}  "
        f"dilate_used: {report.dilate_used}  6-CC: {report.six_cc}"
    )
    print(f"  parts: {count_by_part(report.placements)}")

    used = _as_set(report.voxels)
    illegal = count_illegal_overhang_fills(original, used)
    print(f"  illegal overhang fills (must be 0): {illegal}")

    path = out / "bunny_structure.io"
    export_bricks_to_io(bricks, path, name="General structure pass")
    (out / "bunny_structure_report.txt").write_text(
        "General automatic clutch structure (no pillars)\n"
        "Algorithm: fill_enclosed_cavities + close_surface_cracks +\n"
        "choose_column_staples + pack/merge + repair_clutch_cuts\n"
        "Never fill_column_gaps through outside-reachable air.\n\n"
        + format_connectivity_report(conn, bricks)
        + f"\nstructure={report.verdict}\n"
        + f"voxels_added={report.voxels_added} dilate_used={report.dilate_used} "
        + f"six_cc={report.six_cc}\n"
        + f"parts={count_by_part(report.placements)}\n"
        + f"illegal_overhang_fills={illegal}\n",
        encoding="utf-8",
    )

    for old in (
        "bunny_no_pillars.io",
        "bunny_shape_safe.io",
        "bunny_ZERO_detached.io",
        "bunny_AFTER_fixed_connectivity.io",
    ):
        p = out / old
        if p.exists():
            p.unlink()

    print()
    print(f"Open: {path}")
    if illegal == 0:
        print("Pillar rule OK: no overhang air filled except 1-ring dilate shell.")
    else:
        print(f"WARNING: {illegal} illegal overhang fills.")
    if report.section_count > 1:
        print(
            f"In-solid limit: {report.section_count} clutch sections remain "
            "(floaters with no in-solid cut edge — not pillared)."
        )


if __name__ == "__main__":
    main()
