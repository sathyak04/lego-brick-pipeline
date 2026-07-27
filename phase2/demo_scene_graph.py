"""
Phase 2, Step 1 demo — build a legal stack as a scene graph, export .io.

Blueprint: Phase 2 Scene Graph. No absolute py_above() in the build —
only root_on_ground + stack_on_studs edges.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from export_io import export_bricks_to_io  # noqa: E402
from scene import BrickNode, SceneGraph, root_on_ground, stack_on_studs  # noqa: E402


def build_demo_graph() -> SceneGraph:
    """
    Legal mini wall via DAG edges only:

      plate (root on ground)
        └─ red 2x4 brick   (stacked on plate)
             ├─ blue slope left   (on brick, default face)
             └─ blue slope right  (on brick, default face)
    """
    g = SceneGraph()

    plate = BrickNode(id="plate", part_id="3020.dat", color=14)
    wall = BrickNode(id="wall", part_id="3001.dat", color=4)
    slope_l = BrickNode(id="slope_l", part_id="3039.dat", color=1)
    slope_r = BrickNode(id="slope_r", part_id="3039.dat", color=1)

    g.add_root(plate, root_on_ground("3020.dat"))
    plate.add_child(wall, stack_on_studs("3001.dat"))
    # Two 2x2 slopes cover the 2x4 (sx = ±1), flush — no overhang.
    wall.add_child(slope_l, stack_on_studs("3039.dat", sx=-1.0, sz=0.0))
    wall.add_child(slope_r, stack_on_studs("3039.dat", sx=1.0, sz=0.0))

    return g


def main() -> None:
    g = build_demo_graph()
    bricks = g.to_bricks()
    out = (
        Path(__file__).resolve().parent.parent
        / "output"
        / "phase2_step1_scene.io"
    )
    path = export_bricks_to_io(bricks, out, name="Phase2 Step1 Scene Graph")

    print(f"Wrote: {path}")
    print(f"Nodes: {len(g.iter_nodes())}")
    print("--- scene graph (world poses) ---")
    for n in g.iter_nodes():
        w = g.world_pose(n)
        parent = n.parent.id if n.parent else "(root)"
        print(
            f"  {n.id:10} part={n.part_id}  parent={parent:8}  "
            f"world=({w.x:.0f},{w.y:.0f},{w.z:.0f})"
        )


if __name__ == "__main__":
    main()
