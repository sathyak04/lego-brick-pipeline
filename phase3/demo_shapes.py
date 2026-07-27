"""
Phase 3, Step 2 — More shapes: sphere + ramp → 1x1 voxels → .io

Shows that smooth meshes become blocky LEGO approximations.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import BRICK_H, STUD  # noqa: E402
from mesh import Mesh, make_box, write_obj  # noqa: E402
from voxelize import export_voxels_io, voxelize_solid  # noqa: E402


def make_uv_sphere(
    radius: float,
    stacks: int = 16,
    slices: int = 24,
    cx: float = 0.0,
    cy: float = 0.0,
    cz: float = 0.0,
) -> Mesh:
    """UV sphere centered at (cx,cy,cz), +Y up, radius in LDU."""
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []

    for i in range(stacks + 1):
        v = i / stacks
        phi = v * math.pi  # 0..pi
        y = cy + radius * math.cos(phi)
        ring_r = radius * math.sin(phi)
        for j in range(slices):
            u = j / slices
            theta = u * 2.0 * math.pi
            x = cx + ring_r * math.cos(theta)
            z = cz + ring_r * math.sin(theta)
            verts.append((x, y, z))

    def vid(i: int, j: int) -> int:
        return i * slices + (j % slices)

    for i in range(stacks):
        for j in range(slices):
            a = vid(i, j)
            b = vid(i, j + 1)
            c = vid(i + 1, j)
            d = vid(i + 1, j + 1)
            # skip degenerate caps
            if i != 0:
                faces.append((a, c, b))
            if i != stacks - 1:
                faces.append((b, c, d))

    return Mesh(vertices=verts, faces=faces)


def make_wedge(
    xmin: float, zmin: float,
    xmax: float, zmax: float,
    y0: float, y1: float,
) -> Mesh:
    """
    Ramp / wedge: full height y1 at x=xmin, tapers to y0 at x=xmax.
    Bottom on y=0.. actually bottom face at y=0, top slopes.
    """
    # Corners: bottom rectangle + two top heights
    v = [
        (xmin, 0.0, zmin),  # 0
        (xmax, 0.0, zmin),  # 1
        (xmax, 0.0, zmax),  # 2
        (xmin, 0.0, zmax),  # 3
        (xmin, y1, zmin),   # 4 high
        (xmin, y1, zmax),   # 5 high
        (xmax, y0, zmin),   # 6 low (can be 0)
        (xmax, y0, zmax),   # 7 low
    ]
    f = [
        # bottom
        (0, 2, 1), (0, 3, 2),
        # high end (-X? xmin wall)
        (0, 4, 5), (0, 5, 3),
        # low end
        (1, 2, 7), (1, 7, 6),
        # sides
        (0, 1, 6), (0, 6, 4),
        (3, 5, 7), (3, 7, 2),
        # slope top
        (4, 6, 7), (4, 7, 5),
    ]
    return Mesh(vertices=v, faces=f)


def run_shape(
    name: str,
    mesh: Mesh,
    out: Path,
    color: int,
    use_raycast: bool,
) -> None:
    obj = write_obj(mesh, out / f"{name}.obj")
    voxels = voxelize_solid(mesh, use_raycast=use_raycast)
    io = export_voxels_io(
        voxels,
        out / f"phase3_step2_{name}.io",
        name=f"Phase3 {name}",
        color=color,
    )
    (mn, mx) = mesh.bounds()
    print(f"[{name}]")
    print(f"  mesh:   {obj}")
    print(f"  bounds: {mn} .. {mx}")
    print(f"  voxels: {len(voxels)}  (raycast={use_raycast})")
    print(f"  wrote:  {io}")
    print()


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "output" / "phase3"
    out.mkdir(parents=True, exist_ok=True)

    # Sphere: radius ~ 3 studs, sitting above ground
    r = 3.0 * STUD
    sphere = make_uv_sphere(radius=r, stacks=20, slices=28, cx=r, cy=r, cz=r)

    # Ramp: 6 studs long, 3 studs deep, 4 bricks tall at back → 0 at front
    ramp = make_wedge(
        0.0, 0.0,
        6.0 * STUD, 3.0 * STUD,
        y0=0.0,
        y1=4.0 * BRICK_H,
    )

    # Keep the box too for comparison
    box = make_box(0.0, 0.0, 0.0, 4 * STUD, 3 * BRICK_H, 2 * STUD)

    run_shape("box", box, out, color=4, use_raycast=False)
    run_shape("sphere", sphere, out, color=1, use_raycast=True)
    run_shape("ramp", ramp, out, color=2, use_raycast=True)

    print("Open the three .io files in Studio:")
    print("  box    = solid rectangle (smooth original ≈ LEGO)")
    print("  sphere = blue blob / ball staircase")
    print("  ramp   = green stepped slope")


if __name__ == "__main__":
    main()
