"""
Hollow shell: smooth tiled exterior (0 studs) + studded underside strips.

Rollback: output/phase5/baseline_hollow_shell/
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
from scaffold import shell_plus_scaffold  # noqa: E402
from greedy import consolidate_voxels, count_by_part  # noqa: E402
from connectivity import check_connectivity, format_connectivity_report  # noqa: E402
from plate_bridge import finish_shell_surface, open_cutaway_bricks  # noqa: E402


def fit(mesh, max_studs: float) -> None:
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase5"
    out.mkdir(parents=True, exist_ok=True)

    print("Voxelizing bunny...")
    bunny = load_obj(root / "assets" / "meshes" / "bunny.obj")
    fit(bunny, 28.0)
    solid = voxelize_solid(bunny, use_raycast=True)
    print(f"  solid={len(solid)}")

    print("Hollow shell + merge...")
    shell, interior, _sc, _ = shell_plus_scaffold(
        solid, stride=99, floor_every=0, belt_every=0, pin_columns=False
    )
    print(
        f"  shell={len(shell)} cavities={len(interior)} "
        f"({100 * len(interior) / len(solid):.0f}% hollow)"
    )
    placements = consolidate_voxels(shell, color=15, stagger=True)
    print(f"  shell parts={len(placements)} {count_by_part(placements)}")

    solid_cells = {(v.ix, v.iy, v.iz) for v in solid}
    print("Under-plate strips then tile exterior tops only (no cavity tiles)...")
    all_bricks, stats = finish_shell_surface(
        placements,
        shell_color=15,
        tile_color=15,
        plate_color=72,
        solid=solid_cells,
    )
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
    print(format_connectivity_report(check_connectivity(all_bricks), all_bricks))

    mix: dict[str, int] = {}
    for b in all_bricks:
        mix[b.part_id] = mix.get(b.part_id, 0) + 1
    print(f"  part mix: {mix}")

    opened = open_cutaway_bricks(all_bricks, gap_studs=2.0)
    path = out / "SEE_HOLLOW_OPEN.io"
    export_bricks_to_io(opened, path, name="Smooth exterior + under-plate strips")
    export_bricks_to_io(all_bricks, out / "bunny_hollow_merged.io", name="Smooth exterior")
    export_bricks_to_io(opened, out / "SEE_HOLLOW_MERGED_half_cut.io", name="open")
    export_bricks_to_io(opened, out / "SEE_LATTICE_half_cut.io", name="open")

    (out / "bunny_hollow_lattice_report.txt").write_text(
        "Smooth tiled exterior (0 exposed studs) + studded underside strips.\n"
        f"stats={stats}\nmix={mix}\n"
        + format_connectivity_report(check_connectivity(all_bricks), all_bricks),
        encoding="utf-8",
    )

    print()
    print(f"OPEN THIS: {path}")
    print(
        f"Exposed top studs: {stats['uncovered_studs']} | "
        f"collisions: {stats['collisions']} | "
        f"detached: {stats['sections_final']}"
    )


if __name__ == "__main__":
    main()
