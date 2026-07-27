"""
Phase 4, Step 1 — Greedy consolidation of 1x1 voxels into larger bricks.

Blueprint anchor: Phase 4 Brick Optimizer (Part Count Bloat Control).

Spatial math (per brick layer iy):
  1. Occupancy is a 2D set of stud cells (ix, iz).
  2. Candidate bricks from catalog packing_templates("brick") (largest
     footprint first), each with optional 90° yaw.
  3. Greedy: scan the layer; wherever a candidate fully fits in remaining
     cells, place it and remove those cells.
  4. Stagger (interlock): on odd layers, prefer scan offsets so vertical
     seams don't line up (like a brick wall).
  5. World pose: footprint corner (ix, iz) → origin at stud center of the
     rectangle; LDraw top-origin y = -(iy+1)*24; apply yaw matrix if any.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))

from catalog import BRICK_H, STUD, packing_templates  # noqa: E402
from export_io import Brick, export_bricks_to_io  # noqa: E402
from voxelize import Voxel  # noqa: E402

# LDraw a..i : identity and +90° about Y (vertical)
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
YAW_90 = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)


@dataclass(frozen=True)
class Template:
    part_id: str
    w: int  # footprint studs on +X before yaw
    d: int  # footprint studs on +Z before yaw
    rot: tuple[float, ...]

    @property
    def world_w(self) -> int:
        return self.d if self.rot != IDENTITY else self.w

    @property
    def world_d(self) -> int:
        return self.w if self.rot != IDENTITY else self.d


def _brick_templates() -> list[Template]:
    """All rectangular brick footprints from the System catalog."""
    return [
        Template(t.part_id, t.w, t.d, t.rot) for t in packing_templates("brick")
    ]


# Lazily resolved so catalog expansion is picked up without circular import issues
TEMPLATES: list[Template] = []


def _templates() -> list[Template]:
    global TEMPLATES
    if not TEMPLATES:
        TEMPLATES = _brick_templates()
    return TEMPLATES


@dataclass(frozen=True)
class Placement:
    part_id: str
    color: int
    ix: int
    iy: int
    iz: int
    w: int
    d: int
    rot: tuple[float, ...]


def _fits(occ: set[tuple[int, int]], ix: int, iz: int, w: int, d: int) -> bool:
    for x in range(ix, ix + w):
        for z in range(iz, iz + d):
            if (x, z) not in occ:
                return False
    return True


def _consume(occ: set[tuple[int, int]], ix: int, iz: int, w: int, d: int) -> None:
    for x in range(ix, ix + w):
        for z in range(iz, iz + d):
            occ.discard((x, z))


def consolidate_layer(
    cells: set[tuple[int, int]],
    iy: int,
    color: int,
    stagger: bool,
) -> list[Placement]:
    """Greedy pack one Z/X layer of occupied studs."""
    occ = set(cells)
    placed: list[Placement] = []

    # Stagger: on odd layers, iterate x starting at 1 to shift seams.
    x_bias = 1 if (stagger and iy % 2 == 1) else 0

    for tmpl in _templates():
        w, d = tmpl.world_w, tmpl.world_d
        if not occ:
            break
        xs = sorted({x for x, _ in occ})
        zs = sorted({z for _, z in occ})
        # Rotate starting x for stagger without missing cells
        if x_bias:
            xs = [x for x in xs if (x - x_bias) % 2 == 0] + [
                x for x in xs if (x - x_bias) % 2 != 0
            ]

        progress = True
        while progress and occ:
            progress = False
            for ix in list(xs):
                for iz in zs:
                    if (ix, iz) not in occ:
                        continue
                    if _fits(occ, ix, iz, w, d):
                        placed.append(
                            Placement(
                                part_id=tmpl.part_id,
                                color=color,
                                ix=ix,
                                iy=iy,
                                iz=iz,
                                w=w,
                                d=d,
                                rot=tmpl.rot,
                            )
                        )
                        _consume(occ, ix, iz, w, d)
                        progress = True
            # refresh candidate coords
            xs = sorted({x for x, _ in occ})
            zs = sorted({z for _, z in occ})
            if x_bias:
                xs = [x for x in xs if (x - x_bias) % 2 == 0] + [
                    x for x in xs if (x - x_bias) % 2 != 0
                ]

    if occ:
        # Should be empty if 1x1 template exists; belt-and-suspenders
        for ix, iz in sorted(occ):
            placed.append(
                Placement("3005.dat", color, ix, iy, iz, 1, 1, IDENTITY)
            )
        occ.clear()

    return placed


def consolidate_voxels(
    voxels: list[Voxel],
    color: int = 4,
    stagger: bool = True,
) -> list[Placement]:
    """Merge all layers of 1x1 voxels into larger bricks."""
    by_layer: dict[int, set[tuple[int, int]]] = {}
    for v in voxels:
        by_layer.setdefault(v.iy, set()).add((v.ix, v.iz))

    out: list[Placement] = []
    for iy in sorted(by_layer):
        out.extend(consolidate_layer(by_layer[iy], iy, color, stagger=stagger))
    return out


def placements_to_bricks(placements: list[Placement]) -> list[Brick]:
    bricks: list[Brick] = []
    for p in placements:
        # Origin at footprint center (stud space)
        sx = p.ix + p.w / 2.0
        sz = p.iz + p.d / 2.0
        x = sx * STUD
        z = sz * STUD
        y = -float((p.iy + 1) * BRICK_H)
        a, b, c, d, e, f, g, h, i = p.rot
        bricks.append(
            Brick(
                part_id=p.part_id,
                color=p.color,
                x=x,
                y=y,
                z=z,
                a=a, b=b, c=c, d=d, e=e, f=f, g=g, h=h, i=i,
            )
        )
    return bricks


def count_by_part(placements: list[Placement]) -> dict[str, int]:
    tallies: dict[str, int] = {}
    for p in placements:
        tallies[p.part_id] = tallies.get(p.part_id, 0) + 1
    return tallies


def export_placements_io(
    placements: list[Placement],
    path: Path,
    name: str,
) -> Path:
    return export_bricks_to_io(placements_to_bricks(placements), path, name=name)
