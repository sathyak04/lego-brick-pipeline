"""
Phase 3 finish — large-scale solid vs shell voxelization.

Exports for teapot / bunny / hammer at ~24–28 studs:
  *_large_solid.io  — fully filled 1x1s
  *_large_shell.io  — exterior skin only (hollow interior)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import BRICK_H, STUD  # noqa: E402
from export_io import export_bricks_to_io  # noqa: E402
from mesh import Mesh, load_obj, make_box, make_hammer, write_obj  # noqa: E402
from voxelize import (  # noqa: E402
    Voxel,
    export_voxels_io,
    shell_from_solid,
    voxelize_solid,
    voxels_to_bricks,
)


def fit_mesh_to_studs(mesh: Mesh, max_studs: float) -> Mesh:
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    if longest <= 1e-9:
        raise ValueError("empty mesh")
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))
    return mesh


def fit_box_parts(parts: list[Mesh], max_studs: float) -> list[Mesh]:
    xs = [x for m in parts for x, _, _ in m.vertices]
    ys = [y for m in parts for _, y, _ in m.vertices]
    zs = [z for m in parts for _, _, z in m.vertices]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    zmin, zmax = min(zs), max(zs)
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    scale = (max_studs * STUD) / longest
    cx, cz = 0.5 * (xmin + xmax), 0.5 * (zmin + zmax)
    for m in parts:
        m.scale(scale)
        m.translate(-cx * scale, -ymin * scale, -cz * scale)
    return parts


def solid_from_boxes(parts: list[Mesh]) -> list[Voxel]:
    cells: set[tuple[int, int, int]] = set()
    for m in parts:
        for v in voxelize_solid(m, use_raycast=False):
            cells.add((v.ix, v.iy, v.iz))
    return [Voxel(*c) for c in sorted(cells)]


def export_pair(
    name: str,
    solid: list[Voxel],
    out: Path,
    color_solid: int,
    color_shell: int,
) -> None:
    shell = shell_from_solid(solid)
    p_solid = export_voxels_io(
        solid,
        out / f"phase3_{name}_large_solid.io",
        name=f"Phase3 {name} LARGE SOLID",
        color=color_solid,
    )
    p_shell = export_voxels_io(
        shell,
        out / f"phase3_{name}_large_shell.io",
        name=f"Phase3 {name} LARGE SHELL",
        color=color_shell,
    )
    saved = 100.0 * (1.0 - len(shell) / max(len(solid), 1))
    print(f"[{name}]")
    print(f"  solid: {len(solid):5d} bricks -> {p_solid.name}")
    print(f"  shell: {len(shell):5d} bricks -> {p_shell.name}  ({saved:.0f}% fewer)")
    print()


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    mesh_dir = root / "assets" / "meshes"
    out = root / "output" / "phase3"
    out.mkdir(parents=True, exist_ok=True)

    large = 26.0  # studs on longest axis — clearly bigger than earlier ~10-14

    # --- teapot ---
    teapot = load_obj(mesh_dir / "teapot.obj")
    fit_mesh_to_studs(teapot, large)
    write_obj(teapot, out / "teapot_large_fitted.obj")
    print("voxelizing teapot (raycast, large)...")
    export_pair("teapot", voxelize_solid(teapot, use_raycast=True), out, 14, 25)

    # --- bunny ---
    bunny = load_obj(mesh_dir / "bunny.obj")
    fit_mesh_to_studs(bunny, large)
    write_obj(bunny, out / "bunny_large_fitted.obj")
    print("voxelizing bunny (raycast, large)...")
    export_pair("bunny", voxelize_solid(bunny, use_raycast=True), out, 15, 1)

    # --- hammer (box union) ---
    parts = [
        make_box(-8, 0, -8, 8, 120, 8),
        make_box(-50, 100, -14, 50, 140, 14),
        make_box(-60, 108, -10, -50, 132, 10),
    ]
    fit_box_parts(parts, large)
    preview = make_hammer()
    fit_mesh_to_studs(preview, large)
    write_obj(preview, out / "hammer_large_fitted.obj")
    print("voxelizing hammer (box union, large)...")
    export_pair("hammer", solid_from_boxes(parts), out, 7, 6)

    # Index
    index = out / "PHASE3_LARGE_INDEX.txt"
    index.write_text(
        "\n".join(
            [
                "Phase 3 finish — LARGE solid vs shell",
                f"Target scale: ~{large:.0f} studs on longest axis",
                "",
                "SOLID = every interior cell filled (heavy, strong-looking)",
                "SHELL = only exterior skin (hollow, far fewer parts)",
                "",
                "Files:",
                "  phase3_teapot_large_solid.io / phase3_teapot_large_shell.io",
                "  phase3_bunny_large_solid.io  / phase3_bunny_large_shell.io",
                "  phase3_hammer_large_solid.io / phase3_hammer_large_shell.io",
                "",
                "Open pairs in Studio and compare part count vs silhouette.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Index: {index}")
    print("Phase 3 shell+solid at large scale complete.")


if __name__ == "__main__":
    main()
