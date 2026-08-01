"""
Phase 4, Step 2 — Hollow shell + simple interior scaffold (MINIMUM pattern).

Blueprint anchor: Phase 4 Slicer Infill / Scaffolding.

This is the baseline lattice only — one reusable pattern for any mesh:
  - Outer shell keeps the silhouette.
  - Interior scaffold = coarse stud-grid columns + optional floor ties / belts.
  - Every kept cell is a subset of the solid (never overhang air).

Richer interiors (denser under cantilevers, different braces, part swaps)
are for the future Agent to iterate using Phase 5 metrics — not this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))

from voxelize import Voxel, shell_from_solid  # noqa: E402


def _as_set(voxels: list[Voxel]) -> set[tuple[int, int, int]]:
    return {(v.ix, v.iy, v.iz) for v in voxels}


def interior_voxels(solid: list[Voxel], shell: list[Voxel] | None = None) -> list[Voxel]:
    """Cells that are solid but not on the exterior skin."""
    if shell is None:
        shell = shell_from_solid(solid)
    shell_set = _as_set(shell)
    return [v for v in solid if (v.ix, v.iy, v.iz) not in shell_set]


def column_scaffold(
    interior: list[Voxel],
    *,
    stride: int = 4,
    floor_every: int = 0,
) -> list[Voxel]:
    """
    Keep interior cells whose (ix, iz) land on a stride grid (vertical columns).

    If floor_every > 0, also keep lattice cells on those layers (horizontal ties).
    """
    if not interior:
        return []

    cells = _as_set(interior)
    ixs = [ix for ix, _, _ in cells]
    izs = [iz for _, _, iz in cells]
    iys = [iy for _, iy, _ in cells]
    ix0, iz0 = min(ixs), min(izs)
    iy_min, iy_max = min(iys), max(iys)

    keep: set[tuple[int, int, int]] = set()

    for ix, iy, iz in cells:
        if (ix - ix0) % stride == 0 and (iz - iz0) % stride == 0:
            keep.add((ix, iy, iz))

    if floor_every > 0:
        for iy in range(iy_min, iy_max + 1):
            if (iy - iy_min) % floor_every != 0:
                continue
            for ix, iy2, iz in cells:
                if iy2 != iy:
                    continue
                if (ix - ix0) % stride == 0 or (iz - iz0) % stride == 0:
                    keep.add((ix, iy, iz))

    return [Voxel(ix, iy, iz) for ix, iy, iz in sorted(keep)]


def belt_floors(interior: list[Voxel], *, belt_every: int) -> list[Voxel]:
    """Full horizontal slabs of interior on every belt_every-th layer."""
    if belt_every <= 0 or not interior:
        return []
    cells = _as_set(interior)
    iy_min = min(iy for _, iy, _ in cells)
    keep: set[tuple[int, int, int]] = set()
    for ix, iy, iz in cells:
        if (iy - iy_min) % belt_every == 0:
            keep.add((ix, iy, iz))
    return [Voxel(ix, iy, iz) for ix, iy, iz in sorted(keep)]


def pin_columns_through_solid(
    keep: set[tuple[int, int, int]],
    solid_set: set[tuple[int, int, int]],
) -> set[tuple[int, int, int]]:
    """
    For every (ix, iz) that already has a kept cell, fill that column
    only where the solid already exists. Never adds overhang air.
    """
    cols = {(ix, iz) for ix, _iy, iz in keep}
    out = set(keep)
    for ix, iy, iz in solid_set:
        if (ix, iz) in cols:
            out.add((ix, iy, iz))
    return out


def thicken_shell_inward(
    solid: list[Voxel],
    shell: list[Voxel],
    *,
    layers: int = 1,
) -> list[Voxel]:
    """Grow shell inward by `layers` (6-connected) while staying inside solid.

    Keeps the model hollow: only cells that are solid and adjacent to the
    current shell (toward the interior) are added — never the full cavity.
    """
    if layers <= 0:
        return list(shell)
    solid_set = _as_set(solid)
    shell_set = _as_set(shell)
    neigh = (
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1),
    )
    grown = set(shell_set)
    frontier = set(shell_set)
    for _ in range(layers):
        nxt: set[tuple[int, int, int]] = set()
        for ix, iy, iz in frontier:
            for dx, dy, dz in neigh:
                n = (ix + dx, iy + dy, iz + dz)
                if n in solid_set and n not in grown:
                    nxt.add(n)
        grown |= nxt
        frontier = nxt
        if not frontier:
            break
    return [Voxel(ix, iy, iz) for ix, iy, iz in sorted(grown)]


def shell_plus_scaffold(
    solid: list[Voxel],
    *,
    stride: int = 4,
    floor_every: int = 3,
    belt_every: int = 0,
    pin_columns: bool = False,
) -> tuple[list[Voxel], list[Voxel], list[Voxel], list[Voxel]]:
    """
    Returns (shell, interior, scaffold, combined).

    combined ⊆ solid always. If pin_columns, only lattice (scaffold/belt)
    XY columns are filled through the solid — not every shell column
    (that would densify back to nearly solid).
    """
    solid_set = _as_set(solid)
    shell = shell_from_solid(solid)
    interior = interior_voxels(solid, shell)
    scaffold = column_scaffold(interior, stride=stride, floor_every=floor_every)
    belts = belt_floors(interior, belt_every=belt_every)

    lattice = _as_set(scaffold) | _as_set(belts)
    if pin_columns:
        lattice = pin_columns_through_solid(lattice, solid_set)

    combined_set = _as_set(shell) | lattice
    combined = [Voxel(ix, iy, iz) for ix, iy, iz in sorted(combined_set)]
    return shell, interior, scaffold, combined
