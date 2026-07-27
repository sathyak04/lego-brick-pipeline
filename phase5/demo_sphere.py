"""
Hollow sphere connectivity test.

Exports only:
  - sphere_full.io       complete hollow connected sphere
  - sphere_half_cut.io   half-cut so the cavity is visible
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase4"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import STUD  # noqa: E402
from demo_shapes import make_uv_sphere  # noqa: E402
from export_io import export_bricks_to_io  # noqa: E402
from voxelize import voxelize_solid  # noqa: E402
from scaffold import shell_plus_scaffold  # noqa: E402
from greedy import consolidate_voxels, count_by_part  # noqa: E402
from connectivity import check_connectivity, format_connectivity_report  # noqa: E402
from plate_bridge import finish_shell_surface, open_cutaway_bricks  # noqa: E402


def fit_sphere(mesh, diameter_studs: float) -> None:
    """Scale so diameter matches, sit bottom on ground, center XZ."""
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((diameter_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase5"
    out.mkdir(parents=True, exist_ok=True)

    diameter = 32.0  # studs — big enough for long strips, still runnable
    print(f"Building UV sphere (diameter={diameter:.0f} studs)...")
    sphere = make_uv_sphere(radius=1.0, stacks=28, slices=40)
    fit_sphere(sphere, diameter)

    print("Voxelizing...")
    solid = voxelize_solid(sphere, use_raycast=True)
    print(f"  solid={len(solid)}")

    print("Hollow shell + merge...")
    shell, interior, _sc, _ = shell_plus_scaffold(
        solid, stride=99, floor_every=0, belt_every=0, pin_columns=False
    )
    hollow_pct = 100.0 * len(interior) / max(len(solid), 1)
    print(
        f"  shell={len(shell)} cavities={len(interior)} "
        f"({hollow_pct:.0f}% hollow)"
    )
    placements = consolidate_voxels(shell, color=15, stagger=True)
    print(f"  shell parts={len(placements)} {count_by_part(placements)}")

    solid_cells = {(v.ix, v.iy, v.iz) for v in solid}
    print("Connect shell (under-plates, staples, exterior tiles)...")
    all_bricks, stats = finish_shell_surface(
        placements,
        shell_color=15,
        tile_color=15,
        plate_color=72,
        solid=solid_cells,
    )
    report = check_connectivity(all_bricks)
    print(
        f"  under_plates={stats['under_plates']} cavity_plates={stats.get('cavity_plates', 0)} "
        f"staples={stats.get('staples', 0)} tiles={stats['tiles']} "
        f"uncovered_studs={stats['uncovered_studs']} collisions={stats['collisions']}"
    )
    print(
        f"  sections: {stats['sections_before']} -> "
        f"{stats['sections_after_under']} (after under) -> "
        f"{stats['sections_final']} (final)"
    )
    print(format_connectivity_report(report, all_bricks))

    opened = open_cutaway_bricks(all_bricks, gap_studs=2.0)
    export_bricks_to_io(all_bricks, out / "sphere_full.io", name="Hollow sphere (full)")
    export_bricks_to_io(
        opened, out / "sphere_half_cut.io", name="Hollow sphere (half-cut)"
    )

    mix: dict[str, int] = {}
    for b in all_bricks:
        mix[b.part_id] = mix.get(b.part_id, 0) + 1

    (out / "sphere_report.txt").write_text(
        f"Hollow sphere diameter={diameter} studs\n"
        f"stats={stats}\nmix={mix}\n"
        + format_connectivity_report(report, all_bricks),
        encoding="utf-8",
    )
    (out / "OPEN_THESE.txt").write_text(
        "Open these two in Studio:\n\n"
        "1. sphere_full.io       — complete hollow connected sphere\n"
        "2. sphere_half_cut.io   — same model, cut in half so the cavity is visible\n",
        encoding="utf-8",
    )

    print()
    print(f"Full:  {out / 'sphere_full.io'}")
    print(f"Half:  {out / 'sphere_half_cut.io'}")
    print(
        f"Exposed top studs: {stats['uncovered_studs']} | "
        f"collisions: {stats['collisions']} | "
        f"detached: {stats['sections_final']}"
    )


if __name__ == "__main__":
    main()
