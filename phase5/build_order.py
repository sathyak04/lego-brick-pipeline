"""
Phase 5, Step 3 — Step-by-step buildability / instruction feasibility.

Blueprint anchor: Phase 5 "Instruction Feasibility"
"Bricks cannot float in mid-air during step 12 waiting for a support
column to be added in step 15."

Spatial model (hollow shells included):
  A piece may be placed when:
    1) its bottom sits on the ground plane, OR
    2) at least one already-placed piece vertically supports it
       (stud↔tube: supporter top ≈ this bottom, XZ overlap ≥ ¼ stud²).

  Same-layer side-touch does NOT unlock placement — that is friction /
  hold-in-air, not a legal instruction step. (Overhang reachability may
  still mark those pieces "supported" in the finished model.)

Algorithm: greedy unlock from ground via directed vertical-support edges.
Returns a placement order when every brick unlocks; otherwise lists
blocked (mid-air) indices.
"""

from __future__ import annotations

import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from catalog import STUD, get_part  # noqa: E402
from export_io import Brick  # noqa: E402

EPS_Y = 2.0  # LDU


@dataclass(frozen=True)
class BuildOrderReport:
    order: list[int]  # placement sequence (prefix if blocked remain)
    blocked_ids: list[int]
    grounded_ids: list[int]

    @property
    def buildable(self) -> bool:
        return len(self.blocked_ids) == 0

    @property
    def step_count(self) -> int:
        return len(self.order)

    @property
    def verdict(self) -> str:
        if self.buildable:
            return f"PASS - buildable in {self.step_count} placement(s)"
        return (
            f"FAIL - {len(self.blocked_ids)} piece(s) need mid-air placement"
        )


def _height(b: Brick) -> float:
    return float(get_part(b.part_id).height_ldu)


def _top(b: Brick) -> float:
    return b.y


def _bottom(b: Brick) -> float:
    return b.y + _height(b)


def _xz_aabb(b: Brick) -> tuple[float, float, float, float]:
    spec = get_part(b.part_id)
    hx = spec.width * STUD / 2.0
    hz = spec.depth * STUD / 2.0
    local = [(-hx, 0.0, -hz), (hx, 0.0, -hz), (hx, 0.0, hz), (-hx, 0.0, hz)]
    xs: list[float] = []
    zs: list[float] = []
    for lx, ly, lz in local:
        wx = b.a * lx + b.d * ly + b.g * lz + b.x
        wz = b.c * lx + b.f * ly + b.i * lz + b.z
        xs.append(wx)
        zs.append(wz)
    return min(xs), max(xs), min(zs), max(zs)


def _overlap_area(a: Brick, b: Brick) -> float:
    ax0, ax1, az0, az1 = _xz_aabb(a)
    bx0, bx1, bz0, bz1 = _xz_aabb(b)
    ox = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    oz = max(0.0, min(az1, bz1) - max(az0, bz0))
    return ox * oz


def _vertical_support(below: Brick, above: Brick) -> bool:
    if abs(_top(below) - _bottom(above)) > EPS_Y:
        return False
    return _overlap_area(below, above) >= (STUD * STUD * 0.25)


def check_build_order(bricks: list[Brick]) -> BuildOrderReport:
    n = len(bricks)
    if n == 0:
        return BuildOrderReport(order=[], blocked_ids=[], grounded_ids=[])

    bottoms = [_bottom(b) for b in bricks]
    # +Y down: ground = largest bottom Y
    ground_y = max(bottoms)
    grounded = [i for i, by in enumerate(bottoms) if abs(by - ground_y) <= EPS_Y]

    # supporters[i] = brick indices that vertically support i from below
    supporters: dict[int, list[int]] = defaultdict(list)
    # dependents[j] = bricks that j supports from above
    dependents: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if _vertical_support(bricks[i], bricks[j]):
                supporters[j].append(i)
                dependents[i].append(j)

    placed: set[int] = set()
    order: list[int] = []
    ready: deque[int] = deque()
    ready_set: set[int] = set()

    def _can_place(idx: int) -> bool:
        if idx in grounded:
            return True
        return any(s in placed for s in supporters[idx])

    for g in grounded:
        ready.append(g)
        ready_set.add(g)

    # Also seed any non-ground brick that somehow already has a supporter
    # in the empty placed set — none; only grounded start.

    while ready:
        u = ready.popleft()
        ready_set.discard(u)
        if u in placed:
            continue
        if not _can_place(u):
            continue
        placed.add(u)
        order.append(u)
        for v in dependents[u]:
            if v not in placed and v not in ready_set and _can_place(v):
                ready.append(v)
                ready_set.add(v)

    blocked = sorted(set(range(n)) - placed)
    return BuildOrderReport(
        order=order,
        blocked_ids=blocked,
        grounded_ids=sorted(grounded),
    )


def format_build_order_report(report: BuildOrderReport, bricks: list[Brick]) -> str:
    lines = [
        f"VERDICT: {report.verdict}",
        f"  total parts:      {len(bricks)}",
        f"  grounded:         {len(report.grounded_ids)}",
        f"  placed in order:  {report.step_count}",
        f"  blocked (mid-air):{len(report.blocked_ids)}",
    ]
    if report.blocked_ids:
        lines.append("  blocked samples (first 15):")
        for i in report.blocked_ids[:15]:
            b = bricks[i]
            lines.append(
                f"    [{i}] {b.part_id} @ ({b.x:.0f},{b.y:.0f},{b.z:.0f})"
            )
        if len(report.blocked_ids) > 15:
            lines.append(f"    ... +{len(report.blocked_ids) - 15} more")
    return "\n".join(lines)
