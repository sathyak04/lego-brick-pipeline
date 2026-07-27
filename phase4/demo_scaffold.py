"""
Phase 4, Step 2 demo — solid vs shell vs shell+scaffold (then greedy merge).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import STUD  # noqa: E402
from mesh import load_obj, make_box  # noqa: E402
from voxelize import Voxel, export_voxels_io, voxelize_solid  # noqa: E402
from greedy import consolidate_voxels, count_by_part, export_placements_io  # noqa: E402
from scaffold import shell_plus_scaffold  # noqa: E402


def fit(mesh, max_studs: float):
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))
    return mesh


def hammer_solid(max_studs: float) -> list[Voxel]:
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
    s = (max_studs * STUD) / longest
    cx, cz = 0.5 * (xmin + xmax), 0.5 * (zmin + zmax)
    cells: set[tuple[int, int, int]] = set()
    for m in parts:
        m.scale(s)
        m.translate(-cx * s, -ymin * s, -cz * s)
        for v in voxelize_solid(m, use_raycast=False):
            cells.add((v.ix, v.iy, v.iz))
    return [Voxel(*c) for c in sorted(cells)]


def run_case(name: str, solid: list[Voxel], out: Path, color: int) -> None:
    shell, interior, scaffold, combined = shell_plus_scaffold(
        solid, stride=4, floor_every=3
    )
    merged = consolidate_voxels(combined, color=color, stagger=True)

    export_voxels_io(solid, out / f"phase4_{name}_solid_1x1.io", f"{name} solid 1x1", color)
    export_voxels_io(shell, out / f"phase4_{name}_shell_1x1.io", f"{name} shell 1x1", color)
    export_voxels_io(
        combined,
        out / f"phase4_{name}_shell_scaffold_1x1.io",
        f"{name} shell+scaffold 1x1",
        color,
    )
    export_placements_io(
        merged,
        out / f"phase4_{name}_shell_scaffold_merged.io",
        f"{name} shell+scaffold MERGED",
    )

    print(f"[{name}]")
    print(f"  solid:              {len(solid):5d} 1x1")
    print(f"  shell only:         {len(shell):5d} 1x1")
    print(f"  interior:           {len(interior):5d} 1x1")
    print(f"  scaffold cols/floors:{len(scaffold):5d} 1x1")
    print(f"  shell+scaffold:     {len(combined):5d} 1x1")
    print(
        f"  merged:             {len(merged):5d} parts  "
        f"{count_by_part(merged)}"
    )
    print(
        f"  vs solid:           "
        f"{100 * (1 - len(merged) / max(len(solid), 1)):.0f}% fewer parts after hollow+merge"
    )
    print()


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase4"
    out.mkdir(parents=True, exist_ok=True)
    meshes = root / "assets" / "meshes"
    scale = 28.0

    print("teapot...")
    teapot = load_obj(meshes / "teapot.obj")
    fit(teapot, scale)
    run_case("teapot", voxelize_solid(teapot, use_raycast=True), out, 14)

    print("bunny...")
    bunny = load_obj(meshes / "bunny.obj")
    fit(bunny, scale)
    run_case("bunny", voxelize_solid(bunny, use_raycast=True), out, 15)

    print("hammer...")
    run_case("hammer", hammer_solid(scale), out, 7)

    (out / "PHASE4_SCAFFOLD_INDEX.txt").write_text(
        "\n".join(
            [
                "Phase 4 Step 2 — hollow shell + simple column scaffold",
                f"Scale ~{scale:.0f} studs; stride=4; floor_every=3",
                "",
                "Per model open:",
                "  *_solid_1x1.io              full fill",
                "  *_shell_1x1.io              hollow skin only",
                "  *_shell_scaffold_1x1.io     skin + sparse internal columns/floors",
                "  *_shell_scaffold_merged.io  same, after greedy big-brick merge",
                "",
                "No fancy beam types yet — Phase 5 will drive that.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Files in {out}")


if __name__ == "__main__":
    main()
