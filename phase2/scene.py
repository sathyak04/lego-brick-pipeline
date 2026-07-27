"""
Phase 2, Step 1 — Scene graph (DAG) of bricks + stud-stack edges.

Blueprint anchor: Phase 2 (Scene Graph & Connection Engine).

Model = Directed Acyclic Graph:
  - Node  = one brick (part + color)
  - Edge  = parent → child connection with a local Transform
  - World pose of a child = parent_world ∘ local_edge_transform

Step 1 only supports axis-aligned stud stacks (translation, optional yaw).
SNOT / hinges come later.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# Phase 1 catalog / exporter live next door
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from catalog import get_part, py_on_ground, studs_to_ldu  # noqa: E402
from export_io import Brick, export_bricks_to_io  # noqa: E402
from transform import Transform  # noqa: E402


@dataclass
class BrickNode:
    """One brick in the scene graph."""

    id: str
    part_id: str
    color: int
    # Local transform relative to parent (ignored for roots — use world_pose).
    local: Transform = field(default_factory=Transform.identity)
    parent: BrickNode | None = None
    children: list[BrickNode] = field(default_factory=list)

    def add_child(self, child: BrickNode, local: Transform) -> BrickNode:
        """Attach child with an edge transform (parent → child)."""
        if child.parent is not None:
            raise ValueError(f"Node '{child.id}' already has a parent")
        child.parent = self
        child.local = local
        self.children.append(child)
        return child


@dataclass
class SceneGraph:
    """Forest of brick DAGs (usually one root)."""

    roots: list[BrickNode] = field(default_factory=list)

    def add_root(self, node: BrickNode, world: Transform) -> BrickNode:
        node.parent = None
        node.local = world  # for roots, local == world
        self.roots.append(node)
        return node

    def world_pose(self, node: BrickNode) -> Transform:
        """Compose transforms from root down to this node."""
        chain: list[BrickNode] = []
        cur: BrickNode | None = node
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        chain.reverse()

        pose = Transform.identity()
        for n in chain:
            pose = pose.compose(n.local)
        return pose

    def iter_nodes(self) -> list[BrickNode]:
        out: list[BrickNode] = []

        def walk(n: BrickNode) -> None:
            out.append(n)
            for c in n.children:
                walk(c)

        for r in self.roots:
            walk(r)
        return out

    def to_bricks(self) -> list[Brick]:
        """Resolve every node to a Phase-1 Brick for .io export."""
        bricks: list[Brick] = []
        for n in self.iter_nodes():
            w = self.world_pose(n)
            bricks.append(
                Brick(
                    part_id=n.part_id,
                    color=n.color,
                    x=w.x,
                    y=w.y,
                    z=w.z,
                    a=w.a,
                    b=w.b,
                    c=w.c,
                    d=w.d,
                    e=w.e,
                    f=w.f,
                    g=w.g,
                    h=w.h,
                    i=w.i,
                )
            )
        return bricks


def stack_on_studs(
    child_part_id: str,
    sx: float = 0.0,
    sz: float = 0.0,
    yaw_180: bool = False,
) -> Transform:
    """
    Edge transform: child sits on parent's TOP studs (both top-origin parts).

      child_origin = parent_origin + R * (sx, -height_child, sz)_ldu

    Optional yaw_180 faces the child the other way (and flips ox/oz).
    """
    spec = get_part(child_part_id)
    ox, oz = spec.ox, spec.oz
    if yaw_180:
        ox, oz = -ox, -oz

    # Relative studs → LDU. Y: up by full child height (-Y direction).
    dx, _, dz = studs_to_ldu(sx + ox, 0.0, sz + oz)
    dy = -spec.height_ldu  # up in LDraw

    if yaw_180:
        return Transform.yaw_180(dx, dy, dz)
    return Transform.translation(dx, dy, dz)


def root_on_ground(part_id: str, sx: float = 0.0, sz: float = 0.0) -> Transform:
    """World transform for a root whose bottom rests on y=0."""
    spec = get_part(part_id)
    py = py_on_ground(part_id)
    x, y, z = studs_to_ldu(sx + spec.ox, py, sz + spec.oz)
    return Transform.translation(x, y, z)
