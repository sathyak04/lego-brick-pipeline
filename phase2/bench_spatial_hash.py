"""
Quick benchmark: spatial hash vs brute-force pair counts / time.

Not a unit test — run manually:
  python phase2/bench_spatial_hash.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from collision import (  # noqa: E402
    _node_box,
    find_collisions,
    find_collisions_bruteforce,
)
from scene import BrickNode, SceneGraph, root_on_ground  # noqa: E402
from spatial_hash import candidate_pairs  # noqa: E402


def make_grid(n: int) -> SceneGraph:
    """n x n grid of 1x1 bricks on the ground (no overlaps)."""
    g = SceneGraph()
    for i in range(n):
        for j in range(n):
            node = BrickNode(id=f"c{i}_{j}", part_id="3005.dat", color=4)
            g.add_root(node, root_on_ground("3005.dat", sx=float(i), sz=float(j)))
    return g


def main() -> None:
    for n in (5, 10, 20, 30):
        g = make_grid(n)
        parts = n * n

        packed = [_node_box(g, node) for node in g.iter_nodes()]
        boxes = [p[3] for p in packed]
        brute_pairs = parts * (parts - 1) // 2
        hash_pairs = len(candidate_pairs(boxes))

        t0 = time.perf_counter()
        h1 = find_collisions_bruteforce(g)
        t_brute = time.perf_counter() - t0

        t0 = time.perf_counter()
        h2 = find_collisions(g)
        t_hash = time.perf_counter() - t0

        assert len(h1) == len(h2) == 0
        print(
            f"{n}x{n} = {parts:4d} parts | "
            f"pair tests brute={brute_pairs:7d}  hash={hash_pairs:5d} | "
            f"time brute={t_brute*1000:7.2f}ms  hash={t_hash*1000:7.2f}ms"
        )


if __name__ == "__main__":
    main()
