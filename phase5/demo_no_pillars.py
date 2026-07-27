"""
Bunny without chin/ear pillars — only voxels inside the sculpted solid.
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
from connect_fix import build_fully_connected, count_6, _as_set  # noqa: E402
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
    print(f"  solid voxels: {len(solid)}  6-CC: {count_6(_as_set(solid))}")

    print("Connect inside solid only (no overhang pillars)...")
    placements, used, _ = build_fully_connected(solid, color=14, close_rounds=2)
    bricks = placements_to_bricks(placements)
    report = check_connectivity(bricks)

    print(format_connectivity_report(report, bricks))
    print(f"  voxels: {len(used)} (raw {len(solid)})")
    print(f"  parts:  {count_by_part(placements)}")

    path = out / "bunny_no_pillars.io"
    export_bricks_to_io(bricks, path, name="No overhang pillars")
    (out / "bunny_no_pillars_report.txt").write_text(
        "No chin/ear pillars.\n"
        "Only original solid + tiny morphological close.\n"
        "Head hangs from neck interlocking, not a column to the ground.\n\n"
        + format_connectivity_report(report, bricks)
        + f"\nvoxels={len(used)} raw={len(solid)}\n"
        + f"parts={count_by_part(placements)}\n",
        encoding="utf-8",
    )

    # Remove older pillar-ish exports so the folder is clear
    for name in ("bunny_shape_safe.io", "bunny_ZERO_detached.io", "bunny_AFTER_fixed_connectivity.io"):
        p = out / name
        if p.exists():
            p.unlink()
            print(f"  removed old {name}")

    print()
    print(f"Open: {path}")
    print("Look under the chin — there should be open air, not a brick column.")
    if report.section_count > 1:
        print(
            f"Still {report.section_count} clutch sections — fix via neck "
            "interlock / denser voxels next, NOT pillars."
        )


if __name__ == "__main__":
    main()
