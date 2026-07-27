"""
Phase 3 — Load real OBJ meshes (+ procedural hammer), voxelize, export .io
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import BRICK_H, STUD  # noqa: E402
from mesh import Mesh, load_obj, make_hammer, write_obj  # noqa: E402
from voxelize import export_voxels_io, voxelize_solid  # noqa: E402


def fit_mesh_to_studs(mesh: Mesh, max_studs: float = 12.0) -> Mesh:
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    sx, sy, sz = xmax - xmin, ymax - ymin, zmax - zmin
    longest = max(sx, sy, sz)
    if longest <= 1e-9:
        raise ValueError("Mesh has zero size")
    mesh.scale((max_studs * STUD) / longest)
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    mesh.translate(-0.5 * (xmin + xmax), -ymin, -0.5 * (zmin + zmax))
    return mesh


def process_mesh(
    mesh: Mesh,
    out_dir: Path,
    *,
    name: str,
    max_studs: float,
    color: int,
    use_raycast: bool,
) -> None:
    print(f"=== {name} ===")
    print(f"  raw: {len(mesh.vertices)} verts, {len(mesh.faces)} tris")
    fit_mesh_to_studs(mesh, max_studs=max_studs)
    (mn, mx) = mesh.bounds()
    print(
        f"  fitted studs ~ "
        f"X={(mx[0]-mn[0])/STUD:.1f}  "
        f"Y={(mx[1]-mn[1])/BRICK_H:.1f} bricks  "
        f"Z={(mx[2]-mn[2])/STUD:.1f}"
    )
    write_obj(mesh, out_dir / f"{name}_fitted.obj")

    # Multi-box solids (hammer) are not a single closed manifold — use bounds
    # per-cell with raycast when possible; for hammer use raycast anyway and
    # also accept AABB union via raycast on merged boxes (may be leaky).
    # Better for hammer: voxelize with bounds test against ANY constituent box
    # by using raycast=False only works for one AABB. So for hammer use raycast;
    # merged boxes often still raycast OK if each is closed and we test OR...
    # Simplest robust path for hammer: custom fill using point-in any box.
    print(f"  voxelizing (raycast={use_raycast})...")
    voxels = voxelize_solid(mesh, use_raycast=use_raycast)
    print(f"  voxels: {len(voxels)}")
    if not voxels:
        print("  SKIP — 0 voxels")
        return
    io = export_voxels_io(
        voxels,
        out_dir / f"phase3_real_{name}.io",
        name=f"Phase3 {name}",
        color=color,
    )
    print(f"  wrote: {io}")
    print()


def voxelize_hammer(out_dir: Path) -> None:
    """Hammer = union of boxes sharing one fitted coordinate frame."""
    from mesh import make_box
    from voxelize import Voxel, voxelize_solid, voxels_to_bricks
    from export_io import export_bricks_to_io

    print("=== hammer (procedural) ===")
    parts = [
        make_box(-8, 0, -8, 8, 120, 8),          # handle
        make_box(-50, 100, -14, 50, 140, 14),     # head
        make_box(-60, 108, -10, -50, 132, 10),    # peen
    ]
    # Union bounds → one shared fit transform
    xs = [x for m in parts for x, _, _ in m.vertices]
    ys = [y for m in parts for _, y, _ in m.vertices]
    zs = [z for m in parts for _, _, z in m.vertices]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    zmin, zmax = min(zs), max(zs)
    longest = max(xmax - xmin, ymax - ymin, zmax - zmin)
    scale = (14.0 * STUD) / longest
    cx, cz = 0.5 * (xmin + xmax), 0.5 * (zmin + zmax)
    for m in parts:
        m.scale(scale)
        m.translate(-cx * scale, -ymin * scale, -cz * scale)

    cells: set[tuple[int, int, int]] = set()
    for m in parts:
        for v in voxelize_solid(m, use_raycast=False):
            cells.add((v.ix, v.iy, v.iz))

    preview = make_hammer()
    fit_mesh_to_studs(preview, max_studs=14.0)
    write_obj(preview, out_dir / "hammer_fitted.obj")

    voxels = [Voxel(ix, iy, iz) for ix, iy, iz in sorted(cells)]
    print(f"  voxels: {len(voxels)}")
    io = export_bricks_to_io(
        voxels_to_bricks(voxels, color=7),
        out_dir / "phase3_real_hammer.io",
        name="Phase3 hammer",
    )
    print(f"  wrote: {io}")
    print()


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    mesh_dir = root / "assets" / "meshes"
    out = root / "output" / "phase3"
    out.mkdir(parents=True, exist_ok=True)

    jobs = [
        ("teapot", mesh_dir / "teapot.obj", 10.0, 14, True),
        ("bunny", mesh_dir / "bunny.obj", 12.0, 15, True),
        ("airboat", mesh_dir / "airboat.obj", 14.0, 1, True),
        ("al", mesh_dir / "al.obj", 12.0, 2, True),
        ("dodecahedron", mesh_dir / "dodecahedron.obj", 8.0, 25, True),
    ]

    for name, path, studs, color, ray in jobs:
        if not path.exists():
            print(f"missing {path}")
            continue
        try:
            process_mesh(
                load_obj(path),
                out,
                name=name,
                max_studs=studs,
                color=color,
                use_raycast=ray,
            )
        except Exception as e:
            print(f"FAILED {name}: {e}\n")

    voxelize_hammer(out)
    print("Open output/phase3/phase3_real_*.io in Studio.")


if __name__ == "__main__":
    main()
