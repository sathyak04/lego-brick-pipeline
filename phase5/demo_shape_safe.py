"""
Rebuild bunny: connected WITHOUT exterior pillars / 1x1 spaghetti.

Open the .io in Studio — shape should look like the bunny again.
Prefer few large bricks (clutch power) over thousands of 1x1s.
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
from connect_fix import build_fully_connected  # noqa: E402
from connectivity import check_connectivity, format_connectivity_report  # noqa: E402


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
    print(f"  solid voxels: {len(solid)}")

    print("Shape-safe connect (local thicken only, big bricks, no pillars)...")
    placements, used, _ = build_fully_connected(solid, color=14, max_dilate=3)
    bricks = placements_to_bricks(placements)
    report = check_connectivity(bricks)

    print(format_connectivity_report(report, bricks))
    print(f"  voxels: {len(used)} (raw solid was {len(solid)})")
    print(f"  parts:  {count_by_part(placements)}")

    path = out / "bunny_shape_safe.io"
    export_bricks_to_io(bricks, path, name="Shape-safe connect (no pillars)")
    (out / "bunny_shape_safe_report.txt").write_text(
        "Shape-safe connectivity\n"
        "No exterior bridges. Large bricks for clutch power.\n"
        "Still solid (not hollow). Hollow only after shape+clutch are good.\n\n"
        + format_connectivity_report(report, bricks)
        + f"\nvoxels={len(used)} raw_solid={len(solid)}\n"
        + f"parts={count_by_part(placements)}\n",
        encoding="utf-8",
    )

    print()
    print(f"Open: {path}")
    print("Expect: bunny shape back, far fewer clutch-power warnings.")
    if report.section_count > 1:
        print(
            f"Note: {report.section_count} sections remain "
            "(would need interior-only fix or denser voxelize — not pillars)."
        )


if __name__ == "__main__":
    main()
