"""
Phase 2, Step 2 — Axis-aligned bounding box (AABB) collision.

Blueprint anchor: Phase 2 Collision Detection + Release Standard
"Strictly Legal Builds" (no intersecting bounding boxes).

Spatial math:
  Each part has a local AABB in LDraw part space (top-origin):
    X,Z from footprint (with ox/oz so slopes match real geometry)
    Y from 0 (top) to +height (bottom), since +Y is down.

  World AABB = transform the 8 local corners by the node's world pose,
  then take min/max per axis.

  Two boxes collide iff they overlap on ALL three axes:
    a.min < b.max AND b.min < a.max   (per axis)
  Exact face-touch (flush stack) does NOT count as a collision.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from catalog import STUD, PartSpec, get_part  # noqa: E402
from scene import BrickNode, SceneGraph  # noqa: E402
from transform import Transform  # noqa: E402


@dataclass(frozen=True)
class AABB:
    """Axis-aligned box in world LDU."""

    xmin: float
    ymin: float
    zmin: float
    xmax: float
    ymax: float
    zmax: float

    def overlaps(self, other: AABB) -> bool:
        """True if volumes intersect (touching faces = False)."""
        return (
            self.xmin < other.xmax
            and other.xmin < self.xmax
            and self.ymin < other.ymax
            and other.ymin < self.ymax
            and self.zmin < other.zmax
            and other.zmin < self.zmax
        )

    def intersection(self, other: AABB) -> AABB | None:
        """Overlap box, or None if no volume intersection."""
        if not self.overlaps(other):
            return None
        return AABB(
            max(self.xmin, other.xmin),
            max(self.ymin, other.ymin),
            max(self.zmin, other.zmin),
            min(self.xmax, other.xmax),
            min(self.ymax, other.ymax),
            min(self.zmax, other.zmax),
        )


def local_aabb(spec: PartSpec) -> AABB:
    """
    Part-local AABB around the LDraw origin.

    ox/oz shift the footprint relative to the origin (slope quirk):
      x in [(-w/2 - ox), (w/2 - ox)] * STUD
      z in [(-d/2 - oz), (d/2 - oz)] * STUD
      y in [0, height]   # top-origin body
    """
    return AABB(
        xmin=(-spec.width / 2.0 - spec.ox) * STUD,
        xmax=(spec.width / 2.0 - spec.ox) * STUD,
        ymin=0.0,
        ymax=float(spec.height_ldu),
        zmin=(-spec.depth / 2.0 - spec.oz) * STUD,
        zmax=(spec.depth / 2.0 - spec.oz) * STUD,
    )


def world_aabb(spec: PartSpec, pose: Transform) -> AABB:
    """Transform local AABB corners → world AABB."""
    local = local_aabb(spec)
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


@dataclass(frozen=True)
class Collision:
    a_id: str
    b_id: str
    a_part: str
    b_part: str
    a_name: str
    b_name: str
    a_pose: tuple[float, float, float]
    b_pose: tuple[float, float, float]
    overlap: AABB


def _node_box(scene: SceneGraph, n: BrickNode) -> tuple[BrickNode, PartSpec, Transform, AABB]:
    spec = get_part(n.part_id)
    pose = scene.world_pose(n)
    return n, spec, pose, world_aabb(spec, pose)


def find_collisions_bruteforce(scene: SceneGraph) -> list[Collision]:
    """O(n²) pairwise AABB tests (reference implementation)."""
    packed = [_node_box(scene, n) for n in scene.iter_nodes()]
    hits: list[Collision] = []
    for i in range(len(packed)):
        for j in range(i + 1, len(packed)):
            hit = _hit_from_packed(packed[i], packed[j])
            if hit is not None:
                hits.append(hit)
    return hits


def _hit_from_packed(
    a: tuple[BrickNode, PartSpec, Transform, AABB],
    b: tuple[BrickNode, PartSpec, Transform, AABB],
) -> Collision | None:
    na, sa, pa, ba = a
    nb, sb, pb, bb = b
    ov = ba.intersection(bb)
    if ov is None:
        return None
    return Collision(
        a_id=na.id,
        b_id=nb.id,
        a_part=na.part_id,
        b_part=nb.part_id,
        a_name=sa.name,
        b_name=sb.name,
        a_pose=(pa.x, pa.y, pa.z),
        b_pose=(pb.x, pb.y, pb.z),
        overlap=ov,
    )


def find_collisions(scene: SceneGraph) -> list[Collision]:
    """
    AABB collisions using a spatial-hash broadphase (Phase 2 Step 4).

    Same results as find_collisions_bruteforce; fewer pair tests on large scenes.
    """
    from spatial_hash import candidate_pairs

    packed = [_node_box(scene, n) for n in scene.iter_nodes()]
    if len(packed) < 2:
        return []

    boxes = [p[3] for p in packed]
    hits: list[Collision] = []
    for pair in candidate_pairs(boxes):
        hit = _hit_from_packed(packed[pair.i], packed[pair.j])
        if hit is not None:
            hits.append(hit)
    return hits


def report_collisions(scene: SceneGraph, title: str = "") -> str:
    """Human-readable PASS/FAIL with who overlaps whom."""
    hits = find_collisions(scene)
    header = f"=== {title} ===\n" if title else ""
    nodes = scene.iter_nodes()
    inventory = [
        f"  - {n.id}: {get_part(n.part_id).name} ({n.part_id}) color={n.color}"
        for n in nodes
    ]

    if not hits:
        return (
            header
            + f"VERDICT: PASS\n"
            + f"Parts checked: {len(nodes)}\n"
            + "Collisions: 0\n"
            + "Inventory:\n"
            + "\n".join(inventory)
        )

    lines = [
        header + "VERDICT: FAIL",
        f"Parts checked: {len(nodes)}",
        f"Collisions: {len(hits)}",
        "Inventory:",
        *inventory,
        "",
        "Overlapping pairs:",
    ]
    for i, h in enumerate(hits, 1):
        o = h.overlap
        dx = o.xmax - o.xmin
        dy = o.ymax - o.ymin
        dz = o.zmax - o.zmin
        lines.append(f"  [{i}] {h.a_id}  overlaps  {h.b_id}")
        lines.append(f"      {h.a_name} ({h.a_part}) @ ({h.a_pose[0]:.0f}, {h.a_pose[1]:.0f}, {h.a_pose[2]:.0f})")
        lines.append(f"      {h.b_name} ({h.b_part}) @ ({h.b_pose[0]:.0f}, {h.b_pose[1]:.0f}, {h.b_pose[2]:.0f})")
        lines.append(
            f"      overlap box LDU: "
            f"X[{o.xmin:.0f}..{o.xmax:.0f}] "
            f"Y[{o.ymin:.0f}..{o.ymax:.0f}] "
            f"Z[{o.zmin:.0f}..{o.zmax:.0f}] "
            f"(size {dx:.0f} x {dy:.0f} x {dz:.0f})"
        )
    return "\n".join(lines)
