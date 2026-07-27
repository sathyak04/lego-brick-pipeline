"""
Phase 2, Step 4 — Spatial hash broadphase for AABB collision.

Blueprint anchor: Phase 2 Collision Detection (spatial-hash).

Spatial math:
  Partition world LDU space into cubic cells of size CELL (default 40 LDU
  = 2 studs). Each AABB is inserted into every cell its volume overlaps:

    ix in floor(xmin/CELL) .. floor((xmax - eps)/CELL)
    (same for y, z)

  Candidate pairs = objects that share at least one cell.
  Narrowphase = exact AABB.overlaps (unchanged).

  Cost: O(n) insert + O(k) pair tests instead of O(n^2), where k << n^2
  when parts are spread out (critical once Phase 3 emits thousands of 1x1s).
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from catalog import STUD  # noqa: E402

# 2 studs — large enough that a 2x4 spans few cells, small enough to cull.
DEFAULT_CELL = 2 * STUD


class _Box(Protocol):
    xmin: float
    ymin: float
    zmin: float
    xmax: float
    ymax: float
    zmax: float


@dataclass(frozen=True)
class HashPair:
    i: int
    j: int


def _cell_range(min_v: float, max_v: float, cell: float) -> range:
    """Inclusive cell index range covering [min_v, max_v]."""
    lo = math.floor(min_v / cell)
    hi = math.floor((max_v - 1e-9) / cell)
    if hi < lo:
        hi = lo
    return range(lo, hi + 1)


def cells_for_aabb(box: _Box, cell: float = DEFAULT_CELL) -> list[tuple[int, int, int]]:
    """All spatial-hash cell keys overlapped by box."""
    keys: list[tuple[int, int, int]] = []
    for ix in _cell_range(box.xmin, box.xmax, cell):
        for iy in _cell_range(box.ymin, box.ymax, cell):
            for iz in _cell_range(box.zmin, box.zmax, cell):
                keys.append((ix, iy, iz))
    return keys


def candidate_pairs(
    boxes: list[_Box],
    cell: float = DEFAULT_CELL,
) -> list[HashPair]:
    """
    Broadphase: return unique index pairs (i < j) that share a hash cell.
    """
    grid: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for idx, box in enumerate(boxes):
        for key in cells_for_aabb(box, cell):
            grid[key].append(idx)

    seen: set[tuple[int, int]] = set()
    pairs: list[HashPair] = []
    for ids in grid.values():
        n = len(ids)
        for a in range(n):
            for b in range(a + 1, n):
                i, j = ids[a], ids[b]
                if i > j:
                    i, j = j, i
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                pairs.append(HashPair(i, j))
    return pairs
