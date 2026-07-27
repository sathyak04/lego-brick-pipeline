"""
AABB collision checks for flat Brick lists (Phase 5 plate bridges).

Reuses Phase 2 AABB math; does not require a SceneGraph.
Flush face-touch (legal stack) is NOT a collision.
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
        x=b.x, y=b.y, z=b.z,
        a=b.a, b=b.b, c=b.c, d=b.d, e=b.e, f=b.f, g=b.g, h=b.h, i=b.i,
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
