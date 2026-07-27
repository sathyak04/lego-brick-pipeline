"""
Phase 4, Step 1 demo — merge 1x1 voxels into larger bricks; compare .io files.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import STUD  # noqa: E402
from mesh import load_obj, make_box  # noqa: E402
from voxelize import export_voxels_io, shell_from_solid, voxelize_solid  # noqa: E402
from greedy import (  # noqa: E402
    consolidate_voxels,
    count_by_part,
    export_placements_io,
)


def fit(mesh, max_studs: float):
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))
    return mesh


def run_case(name: str, voxels, out: Path, color: int) -> None:
    before = len(voxels)
    export_voxels_io(
        voxels,
        out / f"phase4_{name}_before_1x1.io",
        name=f"Phase4 {name} BEFORE 1x1",
        color=color,
    )
    merged = consolidate_voxels(voxels, color=color, stagger=True)
    after = len(merged)
    export_placements_io(
        merged,
        out / f"phase4_{name}_after_merged.io",
        name=f"Phase4 {name} AFTER merged",
    )
    tallies = count_by_part(merged)
    saved = 100.0 * (1.0 - after / max(before, 1))
    print(f"[{name}]")
    print(f"  before: {before} x 1x1")
    print(f"  after:  {after} parts  ({saved:.0f}% fewer pieces)")
    print(f"  mix:    {tallies}")
    print(f"  files:  phase4_{name}_before_1x1.io / phase4_{name}_after_merged.io")
    print()


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase4"
    out.mkdir(parents=True, exist_ok=True)
    meshes = root / "assets" / "meshes"

    # Large display scale — more voxels = more silhouette detail before merge
    scale = 40.0

    teapot = load_obj(meshes / "teapot.obj")
    fit(teapot, scale)
    print("voxelizing teapot shell...")
    tea_voxels = shell_from_solid(voxelize_solid(teapot, use_raycast=True))
    run_case("teapot_shell", tea_voxels, out, color=14)

    bunny = load_obj(meshes / "bunny.obj")
    fit(bunny, scale)
    print("voxelizing bunny shell...")
    bun_voxels = shell_from_solid(voxelize_solid(bunny, use_raycast=True))
    run_case("bunny_shell", bun_voxels, out, color=15)

    # Hammer via box union
    parts = [
        make_box(-8, 0, -8, 8, 120, 8),
        make_box(-50, 100, -14, 50, 140, 14),
        make_box(-60, 108, -10, -50, 132, 10),
    ]
    xs = [x for m in parts for x, _, _ in m.vertices]
    ys = [y for m in parts for _, y, _ in m.vertices]
    zs = [z for m in parts for _, _, z in m.vertices]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    zmin, zmax = min(zs), max(zs)
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    s = (scale * STUD) / longest
    cx, cz = 0.5 * (xmin + xmax), 0.5 * (zmin + zmax)
    cells = set()
    for m in parts:
        m.scale(s)
        m.translate(-cx * s, -ymin * s, -cz * s)
        for v in voxelize_solid(m, use_raycast=False):
            cells.add((v.ix, v.iy, v.iz))
    from voxelize import Voxel

    ham = shell_from_solid([Voxel(*c) for c in cells])
    print("merging hammer shell...")
    run_case("hammer_shell", ham, out, color=7)

    print(f"Open before/after pairs in: {out}")
    (out / "PHASE4_LARGE_INDEX.txt").write_text(
        "\n".join(
            [
                f"Phase 4 greedy merge at ~{scale:.0f} studs (longest axis)",
                "",
                "Compare:",
                "  *_before_1x1.io  = naive voxels",
                "  *_after_merged.io = consolidated bricks",
                "",
                "Larger scale = more silhouette detail; merge still cuts part count.",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
