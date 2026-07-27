"""
Phase 3, Step 1 — Naive solid voxelizer → 1x1 brick cells.

Blueprint anchor: Phase 3 Naive Mesh-to-Brick Voxelizer.

Spatial math:
  1. Mesh vertices are treated as LDU with +Y up (OBJ convention).
  2. Convert to LDraw (-Y up) when placing bricks: y_ldraw = -y_mesh.
  3. Grid pitch:
       X/Z cell = 1 stud = 20 LDU
       Y cell   = 1 brick = 24 LDU
  4. For each cell, test the cell CENTER in mesh space.
     Step 1 solid fill: axis-aligned bounds test for boxes, plus a
     generic ray–triangle winding test for arbitrary OBJ meshes.
  5. Each filled cell → one 3005.dat (Brick 1x1).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase2"))

from catalog import BRICK_H, STUD, get_part  # noqa: E402
from export_io import Brick, export_bricks_to_io  # noqa: E402
from mesh import Mesh  # noqa: E402


@dataclass(frozen=True)
class Voxel:
    """Grid index of a filled 1x1 brick cell."""

    ix: int  # studs on X
    iy: int  # brick layers up from mesh floor
    iz: int  # studs on Z


def _ray_hits_triangle(
    ox: float, oy: float, oz: float,
    dx: float, dy: float, dz: float,
    a, b, c,
) -> float | None:
    """
    Möller–Trumbore ray/triangle. Returns t >= 0 or None.
    Ray: origin + t * dir.
    """
    eps = 1e-8
    ax, ay, az = a
    bx, by, bz = b
    cx, cy, cz = c

    e1x, e1y, e1z = bx - ax, by - ay, bz - az
    e2x, e2y, e2z = cx - ax, cy - ay, cz - az

    # p = dir × e2
    px = dy * e2z - dz * e2y
    py = dz * e2x - dx * e2z
    pz = dx * e2y - dy * e2x

    det = e1x * px + e1y * py + e1z * pz
    if abs(det) < eps:
        return None
    inv = 1.0 / det

    sx, sy, sz = ox - ax, oy - ay, oz - az
    u = (sx * px + sy * py + sz * pz) * inv
    if u < 0.0 or u > 1.0:
        return None

    # q = s × e1
    qx = sy * e1z - sz * e1y
    qy = sz * e1x - sx * e1z
    qz = sx * e1y - sy * e1x
    v = (dx * qx + dy * qy + dz * qz) * inv
    if v < 0.0 or u + v > 1.0:
        return None

    t = (e2x * qx + e2y * qy + e2z * qz) * inv
    if t < eps:
        return None
    return t


def point_inside_mesh(mesh: Mesh, x: float, y: float, z: float) -> bool:
    """
    Inside test via +X raycast odd-crossing rule (closed mesh).
    """
    hits: list[float] = []
    for i0, i1, i2 in mesh.faces:
        t = _ray_hits_triangle(
            x, y, z, 1.0, 0.0, 0.0,
            mesh.vertices[i0], mesh.vertices[i1], mesh.vertices[i2],
        )
        if t is not None:
            hits.append(t)
    # Unique-ish crossings (avoid double-counting edges)
    hits.sort()
    uniq: list[float] = []
    for t in hits:
        if not uniq or abs(t - uniq[-1]) > 1e-5:
            uniq.append(t)
    return (len(uniq) % 2) == 1


def point_inside_bounds(
    mesh: Mesh, x: float, y: float, z: float, pad: float = 1e-6
) -> bool:
    """Fast path for boxes: AABB solid fill."""
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()
    return (
        xmin + pad <= x <= xmax - pad
        and ymin + pad <= y <= ymax - pad
        and zmin + pad <= z <= zmax - pad
    )


def voxelize_solid(
    mesh: Mesh,
    *,
    use_raycast: bool = False,
) -> list[Voxel]:
    """
    Fill every brick-sized cell whose center lies inside the mesh.

    Mesh coords: LDU, +Y up.
    Grid aligned to world origin; cells cover
      X: [ix*20, (ix+1)*20)
      Y: [iy*24, (iy+1)*24)
      Z: [iz*20, (iz+1)*20)
    Center tested at (ix+0.5)*20, (iy+0.5)*24, (iz+0.5)*20.
    """
    (xmin, ymin, zmin), (xmax, ymax, zmax) = mesh.bounds()

    ix0 = int(xmin // STUD)
    ix1 = int((xmax - 1e-9) // STUD)
    iy0 = int(ymin // BRICK_H)
    iy1 = int((ymax - 1e-9) // BRICK_H)
    iz0 = int(zmin // STUD)
    iz1 = int((zmax - 1e-9) // STUD)

    inside = point_inside_mesh if use_raycast else point_inside_bounds
    filled: list[Voxel] = []
    for iy in range(iy0, iy1 + 1):
        for iz in range(iz0, iz1 + 1):
            for ix in range(ix0, ix1 + 1):
                cx = (ix + 0.5) * STUD
                cy = (iy + 0.5) * BRICK_H
                cz = (iz + 0.5) * STUD
                if inside(mesh, cx, cy, cz):
                    filled.append(Voxel(ix, iy, iz))
    return filled


def shell_from_solid(solid: list[Voxel]) -> list[Voxel]:
    """
    Keep only exterior voxels: a filled cell that has at least one
    6-neighbor (face-adjacent) missing from the solid set.

    Spatial idea: solid = volume; shell = cells on the boundary with air.
    Interior cavities are hollowed out (fewer parts, still holds the shape).
    """
    filled = {(v.ix, v.iy, v.iz) for v in solid}
    neigh = (
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1),
    )
    shell: list[Voxel] = []
    for ix, iy, iz in filled:
        for dx, dy, dz in neigh:
            if (ix + dx, iy + dy, iz + dz) not in filled:
                shell.append(Voxel(ix, iy, iz))
                break
    return shell


def voxels_to_bricks(voxels: list[Voxel], color: int = 4) -> list[Brick]:
    """
    Place each voxel as a 1x1 brick (3005.dat).

    Convert mesh +Y up → LDraw -Y up.
    1x1 origin is ON its stud; grid ix maps to stud sx = ix + 0.5
    so the brick body covers [ix, ix+1] in stud space.
    Layer iy: bottom on mesh y = iy*24 → LDraw top-origin y = -(iy+1)*24.
    """
    part = "3005.dat"
    get_part(part)  # catalog guard
    bricks: list[Brick] = []
    for v in voxels:
        sx = v.ix + 0.5
        sz = v.iz + 0.5
        # top-origin: bottom at mesh_y = iy*BRICK_H → origin at (iy+1)*BRICK_H above 0 in up-space
        # LDraw y = -origin_up
        y = -float((v.iy + 1) * BRICK_H)
        x = sx * STUD
        z = sz * STUD
        bricks.append(Brick(part_id=part, color=color, x=x, y=y, z=z))
    return bricks


def export_voxels_io(
    voxels: list[Voxel],
    path: Path,
    name: str = "Phase3 Voxels",
    color: int = 4,
) -> Path:
    return export_bricks_to_io(voxels_to_bricks(voxels, color=color), path, name=name)
