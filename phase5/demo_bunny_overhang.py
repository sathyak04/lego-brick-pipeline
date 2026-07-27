"""
Phase 5 Step 2 demo — bunny overhang check + red/white Studio view.
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
from overhang import (  # noqa: E402
    check_overhangs,
    colorize_support,
    format_overhang_report,
)
from balance import check_balance, format_report as format_balance  # noqa: E402


def fit(mesh, max_studs: float):
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))


def build_bunny_bricks(max_studs: float = 28.0):
    root = Path(__file__).resolve().parent.parent
    bunny = load_obj(root / "assets" / "meshes" / "bunny.obj")
    fit(bunny, max_studs)
    solid = voxelize_solid(bunny, use_raycast=True)
    _s, _i, _c, hollow = shell_plus_scaffold(solid, stride=4, floor_every=3)
    merged = consolidate_voxels(hollow, color=15, stagger=True)
    return placements_to_bricks(merged)


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "output" / "phase5"
    out.mkdir(parents=True, exist_ok=True)

    print("Building bunny...")
    bricks = build_bunny_bricks(28.0)

    overhang = check_overhangs(bricks)
    balance = check_balance(bricks, min_margin_studs=1.0)

    otext = format_overhang_report(overhang, bricks)
    btext = format_balance(balance)
    print(otext)
    print()
    print(btext)

    colored = colorize_support(bricks, overhang)
    export_bricks_to_io(
        colored,
        out / "bunny_overhang_red_unsupported.io",
        name="RED=unsupported WHITE=supported",
    )

    report = (
        "Phase 5 Step 2 — Overhang / support\n"
        "RED bricks in the .io are unsupported (no path from ground).\n"
        "Compare to Studio Stability highlights.\n\n"
        + otext
        + "\n\n"
        + "Balance (Step 1):\n"
        + btext
        + "\n"
    )
    (out / "bunny_overhang_report.txt").write_text(report, encoding="utf-8")

    print()
    print("Open this in Studio (red = would fall / unsupported):")
    print(f"  {out / 'bunny_overhang_red_unsupported.io'}")
    print(f"Report: {out / 'bunny_overhang_report.txt'}")


if __name__ == "__main__":
    main()
