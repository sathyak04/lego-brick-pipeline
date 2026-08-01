"""
Phase 1 — Rectangular System part catalog.

Expanded from the original 10-part seed to common System bricks / plates /
tiles with known LDraw IDs (axis-aligned stud footprints only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


STUD = 20
PLATE_H = 8
BRICK_H = 24

PartKind = Literal["brick", "plate", "tile", "slope"]


@dataclass(frozen=True)
class PartSpec:
    part_id: str
    name: str
    width: int
    depth: int
    height_ldu: int
    kind: PartKind = "brick"
    ox: float = 0.0
    oz: float = 0.0
    studs: tuple[tuple[float, float], ...] | None = None
    # Occupied cells in the W×D grid (i, j) with (0,0)=min corner.
    # None → full rectangle. Used for L-corners etc.
    occupied: tuple[tuple[int, int], ...] | None = None

    def is_rectangular(self) -> bool:
        if self.occupied is None:
            return True
        return len(self.occupied) == self.width * self.depth


# Explicit (part_id, name, w, d, height, kind) — one row per LDraw file.
_PART_TABLE: list[tuple[str, str, int, int, int, PartKind]] = [
    # Bricks
    ("3005.dat", "Brick 1x1", 1, 1, BRICK_H, "brick"),
    ("3004.dat", "Brick 1x2", 2, 1, BRICK_H, "brick"),
    ("3622.dat", "Brick 1x3", 3, 1, BRICK_H, "brick"),
    ("3010.dat", "Brick 1x4", 4, 1, BRICK_H, "brick"),
    ("3009.dat", "Brick 1x6", 6, 1, BRICK_H, "brick"),
    ("3008.dat", "Brick 1x8", 8, 1, BRICK_H, "brick"),
    ("3003.dat", "Brick 2x2", 2, 2, BRICK_H, "brick"),
    ("3002.dat", "Brick 2x3", 3, 2, BRICK_H, "brick"),
    ("3001.dat", "Brick 2x4", 4, 2, BRICK_H, "brick"),
    ("2456.dat", "Brick 2x6", 6, 2, BRICK_H, "brick"),
    ("3007.dat", "Brick 2x8", 8, 2, BRICK_H, "brick"),
    # Plates
    ("3024.dat", "Plate 1x1", 1, 1, PLATE_H, "plate"),
    ("3023.dat", "Plate 1x2", 2, 1, PLATE_H, "plate"),
    ("3623.dat", "Plate 1x3", 3, 1, PLATE_H, "plate"),
    ("3710.dat", "Plate 1x4", 4, 1, PLATE_H, "plate"),
    ("3666.dat", "Plate 1x6", 6, 1, PLATE_H, "plate"),
    ("3460.dat", "Plate 1x8", 8, 1, PLATE_H, "plate"),
    ("3022.dat", "Plate 2x2", 2, 2, PLATE_H, "plate"),
    ("3021.dat", "Plate 2x3", 3, 2, PLATE_H, "plate"),
    ("3020.dat", "Plate 2x4", 4, 2, PLATE_H, "plate"),
    ("3795.dat", "Plate 2x6", 6, 2, PLATE_H, "plate"),
    ("3034.dat", "Plate 2x8", 8, 2, PLATE_H, "plate"),
    ("3031.dat", "Plate 4x4", 4, 4, PLATE_H, "plate"),
    ("3032.dat", "Plate 4x6", 6, 4, PLATE_H, "plate"),
    ("3035.dat", "Plate 4x8", 8, 4, PLATE_H, "plate"),
    ("3958.dat", "Plate 6x6", 6, 6, PLATE_H, "plate"),
    ("3036.dat", "Plate 6x8", 8, 6, PLATE_H, "plate"),
    ("41539.dat", "Plate 8x8", 8, 8, PLATE_H, "plate"),
    # Tiles
    ("3070b.dat", "Tile 1x1", 1, 1, PLATE_H, "tile"),
    ("3069b.dat", "Tile 1x2", 2, 1, PLATE_H, "tile"),
    ("63864.dat", "Tile 1x3", 3, 1, PLATE_H, "tile"),
    ("2431.dat", "Tile 1x4", 4, 1, PLATE_H, "tile"),
    ("6636.dat", "Tile 1x6", 6, 1, PLATE_H, "tile"),
    ("4162.dat", "Tile 1x8", 8, 1, PLATE_H, "tile"),
    ("3068b.dat", "Tile 2x2", 2, 2, PLATE_H, "tile"),
    ("26603.dat", "Tile 2x3", 3, 2, PLATE_H, "tile"),
    ("87079.dat", "Tile 2x4", 4, 2, PLATE_H, "tile"),
    ("69729.dat", "Tile 2x6", 6, 2, PLATE_H, "tile"),
    ("1751.dat", "Tile 4x4", 4, 4, PLATE_H, "tile"),
]


def _build_catalog() -> dict[str, PartSpec]:
    out: dict[str, PartSpec] = {}
    for part_id, name, w, d, h, kind in _PART_TABLE:
        out[part_id] = PartSpec(part_id, name, w, d, h, kind=kind)
    out["3039.dat"] = PartSpec(
        "3039.dat", "Slope 45 2x2", 2, 2, BRICK_H, kind="slope", oz=0.5,
        studs=((-0.5, 0.0), (0.5, 0.0)),
    )
    out["3040.dat"] = PartSpec(
        "3040.dat", "Slope 45 2x1", 2, 1, BRICK_H, kind="slope", oz=0.5,
        studs=((-0.5, 0.0), (0.5, 0.0)),
    )
    # L-corners: bounding box 2x2, three studs (missing +X/+Z corner in local grid)
    _corner_studs = ((-0.5, -0.5), (0.5, -0.5), (-0.5, 0.5))
    _corner_cells = ((0, 0), (1, 0), (0, 1))
    out["2357.dat"] = PartSpec(
        "2357.dat",
        "Brick 2x2 Corner",
        2,
        2,
        BRICK_H,
        kind="brick",
        studs=_corner_studs,
        occupied=_corner_cells,
    )
    out["2420.dat"] = PartSpec(
        "2420.dat",
        "Plate 2x2 Corner",
        2,
        2,
        PLATE_H,
        kind="plate",
        studs=_corner_studs,
        occupied=_corner_cells,
    )
    return out


CATALOG: dict[str, PartSpec] = _build_catalog()

IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
YAW_90 = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)
YAW_180 = (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -1.0)
YAW_270 = (0.0, 0.0, -1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0)


@dataclass(frozen=True)
class PackTemplate:
    part_id: str
    w: int
    d: int
    rot: tuple[float, ...]

    @property
    def world_w(self) -> int:
        return self.d if self.rot != IDENTITY else self.w

    @property
    def world_d(self) -> int:
        return self.w if self.rot != IDENTITY else self.d

    @property
    def area(self) -> int:
        return self.world_w * self.world_d


def get_part(part_id: str) -> PartSpec:
    if part_id not in CATALOG:
        raise KeyError(f"Unknown part '{part_id}'. Catalog has {len(CATALOG)} parts.")
    return CATALOG[part_id]


def iter_parts(kind: PartKind | None = None) -> Iterable[PartSpec]:
    for spec in CATALOG.values():
        if kind is None or spec.kind == kind:
            yield spec


def packing_templates(kind: PartKind) -> list[PackTemplate]:
    """Oriented rectangular footprints for greedy packing, largest area first.

    Non-rectangular parts (L-corners) are skipped — they need an L-packer.
    """
    out: list[PackTemplate] = []
    for spec in iter_parts(kind):
        if not spec.is_rectangular():
            continue
        out.append(PackTemplate(spec.part_id, spec.width, spec.depth, IDENTITY))
        if spec.width != spec.depth:
            out.append(PackTemplate(spec.part_id, spec.width, spec.depth, YAW_90))
    out.sort(key=lambda t: (-t.area, -max(t.world_w, t.world_d), t.part_id))
    return out


def studs_to_ldu(sx: float, py: float, sz: float) -> tuple[float, float, float]:
    return sx * STUD, -py * PLATE_H, sz * STUD


def py_on_ground(part_id: str) -> float:
    return get_part(part_id).height_ldu / PLATE_H


def py_above(base_py: float, base_part_id: str, above_part_id: str) -> float:
    del base_part_id
    return base_py + get_part(above_part_id).height_ldu / PLATE_H
