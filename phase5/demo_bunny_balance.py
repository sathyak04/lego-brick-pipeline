"""
Phase 5 Step 1 demo — bunny balance / tipping check.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase4"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import STUD  # noqa: E402
from mesh import load_obj  # noqa: E402
from voxelize import export_voxels_io, voxelize_solid  # noqa: E402
from greedy import consolidate_voxels, export_placements_io, placements_to_bricks  # noqa: E402
from scaffold import shell_plus_scaffold  # noqa: E402
from balance import check_balance, format_report  # noqa: E402
from export_io import Brick  # noqa: E402


def fit(mesh, max_studs: float):
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))


def build_bunny_merged(max_studs: float = 28.0) -> list[Brick]:
    root = Path(__file__).resolve().parent.parent
    bunny = load_obj(root / "assets" / "meshes" / "bunny.obj")
    fit(bunny, max_studs)
    solid = voxelize_solid(bunny, use_raycast=True)
    _shell, _int, _scaf, hollow = shell_plus_scaffold(solid, stride=4, floor_every=3)
    merged = consolidate_voxels(hollow, color=15, stagger=True)
    return placements_to_bricks(merged)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase5"
    out.mkdir(parents=True, exist_ok=True)

    print("Building bunny (hollow+beams+merged)...")
    bricks = build_bunny_merged(28.0)
    report = check_balance(bricks, min_margin_studs=1.0)
    text = format_report(report)
    print(text)

    # Export the same model so Studio view matches the report
    from export_io import export_bricks_to_io

    export_bricks_to_io(
        bricks,
        out / "bunny_balance_test.io",
        name="Phase5 Bunny balance test",
    )
    (out / "bunny_balance_report.txt").write_text(text + "\n", encoding="utf-8")
    print()
    print(f"Model:  {out / 'bunny_balance_test.io'}")
    print(f"Report: {out / 'bunny_balance_report.txt'}")


if __name__ == "__main__":
    main()
