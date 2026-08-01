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
from scaffold import (  # noqa: E402
    interior_voxels,
    shell_plus_scaffold,
    thicken_shell_inward,
)
from greedy import consolidate_voxels, count_by_part  # noqa: E402
from connectivity import (  # noqa: E402
    check_connectivity,
    classify_weak_edges,
    clutch_strength,
    format_connectivity_report,
    format_weak_edge_diagnosis,
)
from plate_bridge import finish_shell_surface, open_cutaway_bricks  # noqa: E402

# Locked green baseline — do not raise until this diameter stays PASS.
# Scale experiments (18/20+) belong on a branch / one-off override, not here.
BASELINE_DIAMETER_STUDS = 16.0
PASS_SECTIONS = 1
PASS_COLLISIONS = 0
# Soft clutch-strength goals (reported; do not fail the demo on these).
SOFT_WEAK_RATIO = 0.50
SOFT_MEAN_OVERLAP = 2.0
# Early 2-stud hollow wall (still leaves cavity).
SHELL_THICKEN_LAYERS = 1


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

    diameter = BASELINE_DIAMETER_STUDS
    print(f"Building UV sphere (diameter={diameter:.0f} studs, locked baseline)...")
    sphere = make_uv_sphere(radius=1.0, stacks=16, slices=24)
    fit_sphere(sphere, diameter)

    print("Voxelizing...")
    solid = voxelize_solid(sphere, use_raycast=True)
    print(f"  solid={len(solid)}")

    print("Hollow shell + merge...")
    shell, interior, _sc, _ = shell_plus_scaffold(
        solid, stride=99, floor_every=0, belt_every=0, pin_columns=False
    )
    if SHELL_THICKEN_LAYERS > 0:
        before_n = len(shell)
        shell = thicken_shell_inward(solid, shell, layers=SHELL_THICKEN_LAYERS)
        interior = interior_voxels(solid, shell)
        print(
            f"  early hollow thicken +{len(shell) - before_n} "
            f"(layers={SHELL_THICKEN_LAYERS})"
        )
    hollow_pct = 100.0 * len(interior) / max(len(solid), 1)
    print(
        f"  shell={len(shell)} cavities={len(interior)} "
        f"({hollow_pct:.0f}% hollow)"
    )
    placements = consolidate_voxels(shell, color=15, stagger=True, bond=True)
    shell_part_count = len(placements)
    print(f"  shell parts={shell_part_count} {count_by_part(placements)}")

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
    strength = clutch_strength(all_bricks, report)
    weak_diag = classify_weak_edges(
        all_bricks,
        report=report,
        strength=strength,
        shell_count=shell_part_count,
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
    print(format_connectivity_report(report, all_bricks, strength=strength))
    print(format_weak_edge_diagnosis(weak_diag))

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
        + format_connectivity_report(report, all_bricks, strength=strength)
        + "\n"
        + format_weak_edge_diagnosis(weak_diag),
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

    ok = (
        report.section_count == PASS_SECTIONS
        and stats["collisions"] == PASS_COLLISIONS
    )
    if not ok:
        print(
            f"BASELINE FAIL: need {PASS_SECTIONS} section / {PASS_COLLISIONS} collisions; "
            f"got {report.section_count} / {stats['collisions']}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(
        f"BASELINE OK: diameter={diameter:.0f} "
        f"sections={report.section_count} collisions={stats['collisions']} "
        f"weak_edges={strength.weak_edges}/{strength.edge_count} "
        f"mean_overlap={strength.mean_overlap:.2f}"
    )
    soft_ok = (
        strength.weak_ratio <= SOFT_WEAK_RATIO
        and strength.mean_overlap >= SOFT_MEAN_OVERLAP
    )
    print(
        f"SOFT clutch: weak_ratio={100.0 * strength.weak_ratio:.0f}% "
        f"(goal <={100.0 * SOFT_WEAK_RATIO:.0f}%) "
        f"mean={strength.mean_overlap:.2f} (goal >={SOFT_MEAN_OVERLAP:.1f}) "
        f"{'OK' if soft_ok else 'SHORT'}"
    )


if __name__ == "__main__":
    main()
