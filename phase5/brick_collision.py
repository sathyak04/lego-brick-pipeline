"""
AABB collision checks for flat Brick lists (Phase 5 plate bridges).

Reuses Phase 2 AABB math; does not require a SceneGraph.
Flush face-touch (legal stack) is NOT a collision.

CollisionWorld caches AABBs so repeated placement checks stay cheap.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase2"))

from catalog import get_part  # noqa: E402
from export_io import Brick  # noqa: E402
from collision import AABB, local_aabb  # noqa: E402
from transform import Transform  # noqa: E402


def brick_to_transform(b: Brick) -> Transform:
    return Transform(
        x=b.x,
        y=b.y,
        z=b.z,
        a=b.a,
        b=b.b,
        c=b.c,
        d=b.d,
        e=b.e,
        f=b.f,
        g=b.g,
        h=b.h,
        i=b.i,
    )


def brick_aabb(b: Brick) -> AABB:
    spec = get_part(b.part_id)
    local = local_aabb(spec)
    pose = brick_to_transform(b)
    corners = [
        (local.xmin, local.ymin, local.zmin),
        (local.xmin, local.ymin, local.zmax),
        (local.xmin, local.ymax, local.zmin),
        (local.xmin, local.ymax, local.zmax),
        (local.xmax, local.ymin, local.zmin),
        (local.xmax, local.ymin, local.zmax),
        (local.xmax, local.ymax, local.zmin),
        (local.xmax, local.ymax, local.zmax),
    ]
    xs, ys, zs = [], [], []
    for cx, cy, cz in corners:
        wx, wy, wz = pose.apply(cx, cy, cz)
        xs.append(wx)
        ys.append(wy)
        zs.append(wz)
    return AABB(min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


class CollisionWorld:
    """Growing set of bricks with cached AABBs for fast overlap tests."""

    __slots__ = ("bricks", "boxes")

    def __init__(self, bricks: list[Brick] | None = None) -> None:
        self.bricks: list[Brick] = []
        self.boxes: list[AABB] = []
        if bricks:
            for b in bricks:
                self.add(b)

    def add(self, b: Brick) -> None:
        self.bricks.append(b)
        self.boxes.append(brick_aabb(b))

    def collides(self, candidate: Brick) -> bool:
        box = brick_aabb(candidate)
        for other in self.boxes:
            if box.overlaps(other):
                return True
        return False

    def try_add(self, candidate: Brick) -> bool:
        """Add candidate if it does not collide; return True if added."""
        if self.collides(candidate):
            return False
        self.add(candidate)
        return True

    def collides_flat(self, candidate: Brick) -> bool:
        """True if candidate overlaps a plate/tile (ignore brick AABBs).

        1x1 staples often false-positive against neighboring brick boxes; we
        still must never punch through plates/tiles.
        """
        box = brick_aabb(candidate)
        for b, other in zip(self.bricks, self.boxes):
            if get_part(b.part_id).kind not in ("plate", "tile"):
                continue
            if box.overlaps(other):
                return True
        return False

    def collides_except(
        self,
        candidate: Brick,
        ignore: set[int] | None = None,
    ) -> bool:
        """Full AABB collide, skipping bricks whose indices are in `ignore`."""
        box = brick_aabb(candidate)
        skip = ignore or set()
        for i, other in enumerate(self.boxes):
            if i in skip:
                continue
            if box.overlaps(other):
                return True
        return False

    def truncate(self, n: int) -> None:
        """Keep only the first n bricks/boxes."""
        self.bricks = self.bricks[:n]
        self.boxes = self.boxes[:n]


def strip_colliding_extras(
    shell: list[Brick], extras: list[Brick]
) -> tuple[list[Brick], int]:
    """Drop plate/tile extras that fuse into other parts.

    Brick-kind staples (1x1 fills) are kept if their stud cell is unique;
    fused *strips* are what we strip. Shell is never removed.

    Never increases clutch section count — colliding plates that are required
    for connectivity are kept (equator under-bridges often AABB-touch bricks).
    """
    from catalog import get_part  # local to avoid cycles at import
    from connectivity import check_connectivity

    before = check_connectivity(shell + extras).section_count
    index = CollisionWorld(shell)
    kept: list[Brick] = []
    removed = 0
    bricks: list[Brick] = []
    strips: list[Brick] = []
    for b in extras:
        kind = get_part(b.part_id).kind
        if kind in ("plate", "tile"):
            strips.append(b)
        else:
            bricks.append(b)

    # Staples first (vertical clutch spines), skip duplicate 1x1 cells
    seen_cells: set[tuple[int, int, int]] = set()
    for b in bricks:
        if b.part_id == "3005.dat":
            ix = int(round(b.x / 20.0 - 0.5))
            iz = int(round(b.z / 20.0 - 0.5))
            iy = int(round(-b.y / 24.0 - 1.0))
            cell = (ix, iy, iz)
            if cell in seen_cells:
                removed += 1
                continue
            seen_cells.add(cell)
        if index.collides(b):
            removed += 1
            continue
        index.add(b)
        kept.append(b)

    # Plates then tiles — drop fusers only when connectivity does not worsen
    plates = [b for b in strips if get_part(b.part_id).kind == "plate"]
    tiles = [b for b in strips if get_part(b.part_id).kind == "tile"]
    deferred_plates: list[Brick] = []
    for b in plates:
        if index.collides(b):
            deferred_plates.append(b)
            removed += 1
            continue
        index.add(b)
        kept.append(b)
    for b in tiles:
        if index.collides(b):
            removed += 1
            continue
        index.add(b)
        kept.append(b)

    after = check_connectivity(shell + kept).section_count
    if after > before and deferred_plates:
        # Restore colliding plates needed for clutch (under-bridges)
        for b in deferred_plates:
            kept.append(b)
            removed -= 1
        after = check_connectivity(shell + kept).section_count
    if after > before:
        # Fall back to original extras — connectivity wins over clean AABB
        return list(extras), 0
    return kept, removed


def collides_any(candidate: Brick, existing: list[Brick]) -> bool:
    """True if candidate volume intersects any existing part."""
    box = brick_aabb(candidate)
    for other in existing:
        if box.overlaps(brick_aabb(other)):
            return True
    return False


def count_collisions(bricks: list[Brick]) -> int:
    """Pairwise collision count (each overlapping pair once)."""
    boxes = [brick_aabb(b) for b in bricks]
    n = 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i].overlaps(boxes[j]):
                n += 1
    return n
