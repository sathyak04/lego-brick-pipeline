"""
Prove connectivity metric: fix scaffold, remeasure, export for Studio.

BEFORE = old hollow (stride=4, floor_every=3) → ~275 detached sections
AFTER  = shell + belts + denser lattice → sections should crash

Open the AFTER .io in Studio Stability — count should match our print.
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
from greedy import consolidate_voxels, placements_to_bricks  # noqa: E402
from scaffold import shell_plus_scaffold  # noqa: E402
from connectivity import check_connectivity, format_connectivity_report  # noqa: E402


def fit(mesh, max_studs: float) -> None:
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))


def build(solid, **scaffold_kw):
    _s, _i, _c, hollow = shell_plus_scaffold(solid, **scaffold_kw)
    merged = consolidate_voxels(hollow, color=14, stagger=True)  # yellow
    return placements_to_bricks(merged), len(hollow), len(merged)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase5"
    out.mkdir(parents=True, exist_ok=True)

    print("Voxelizing bunny...")
    bunny = load_obj(root / "assets" / "meshes" / "bunny.obj")
    fit(bunny, 28.0)
    solid = voxelize_solid(bunny, use_raycast=True)

    print("\n=== BEFORE (old hollow+sparse beams) ===")
    before_bricks, before_vox, before_parts = build(
        solid, stride=4, floor_every=3, belt_every=0, pin_columns=False
    )
    before = check_connectivity(before_bricks)
    print(format_connectivity_report(before, before_bricks))
    print(f"  voxels={before_vox}  merged_parts={before_parts}")

    print("\n=== AFTER (belts + column pins through solid) ===")
    # Full interior slab every layer + pin every kept XY column through the
    # solid so ears/shell stubs clutch down into the main body.
    after_bricks, after_vox, after_parts = build(
        solid,
        stride=2,
        floor_every=1,
        belt_every=1,
        pin_columns=True,
    )
    after = check_connectivity(after_bricks)
    print(format_connectivity_report(after, after_bricks))
    print(f"  voxels={after_vox}  merged_parts={after_parts}")

    export_bricks_to_io(
        before_bricks,
        out / "bunny_BEFORE_275_sections.io",
        name="BEFORE sparse hollow",
    )
    export_bricks_to_io(
        after_bricks,
        out / "bunny_AFTER_fixed_connectivity.io",
        name="AFTER belts+dense scaffold",
    )

    report = (
        "Connectivity prove-it\n"
        "=====================\n"
        "Our detector counts stud-tube connected components\n"
        "(same idea as Studio Stability 'detached sections').\n\n"
        "BEFORE (old scaffold):\n"
        f"{format_connectivity_report(before, before_bricks)}\n"
        f"  voxels={before_vox}  parts={before_parts}\n\n"
        "AFTER (fixed scaffold):\n"
        f"{format_connectivity_report(after, after_bricks)}\n"
        f"  voxels={after_vox}  parts={after_parts}\n\n"
        "How to verify in Studio:\n"
        "  1) Open bunny_BEFORE_275_sections.io → Stability ~275\n"
        "  2) Open bunny_AFTER_fixed_connectivity.io → Stability should\n"
        "     drop to roughly our AFTER section count below.\n"
        f"\nAFTER detached sections (our meter): {after.section_count}\n"
    )
    (out / "bunny_fix_connectivity_report.txt").write_text(report, encoding="utf-8")

    print("\n--- Open these in Studio Stability ---")
    print(f"  BEFORE: {out / 'bunny_BEFORE_275_sections.io'}")
    print(f"  AFTER:  {out / 'bunny_AFTER_fixed_connectivity.io'}")
    print(f"\nOur meter: {before.section_count} -> {after.section_count}")
    print("If Studio's AFTER number also drops a lot, the detector was right.")


if __name__ == "__main__":
    main()
