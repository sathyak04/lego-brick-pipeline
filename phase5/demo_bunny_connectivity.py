"""
Phase 5 connectivity demo — bunny detached sections vs Studio Stability.
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
from connectivity import (  # noqa: E402
    check_connectivity,
    colorize_by_component,
    format_connectivity_report,
)


def fit(mesh, max_studs: float) -> None:
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

    report = check_connectivity(bricks)
    text = format_connectivity_report(report, bricks)
    print(text)
    print()
    print("Studio showed ~275 detached sections — compare our count above.")

    colored = colorize_by_component(bricks, report)
    path = out / "bunny_connectivity_by_section.io"
    export_bricks_to_io(
        colored,
        path,
        name="WHITE=largest section; other colors=detached islands",
    )

    (out / "bunny_connectivity_report.txt").write_text(
        "Phase 5 — Connectivity (stud-tube clutch only)\n"
        "NO side-touch edges. Matches Studio Stability 'detached sections'.\n"
        "WHITE = largest connected section; other colors = separate islands.\n\n"
        + text
        + "\n",
        encoding="utf-8",
    )

    print()
    print("Open in Studio (white = largest clutch island; colors = detached):")
    print(f"  {path}")
    print(f"Report: {out / 'bunny_connectivity_report.txt'}")


if __name__ == "__main__":
    main()
