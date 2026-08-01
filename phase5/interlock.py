"""
Phase 5 — Structural interlocking / shear-plane audit (the "Squeeze Test").

Blueprint anchor: Release Standard "Structural Interlocking" —
"Prevent vertical shear planes. Bricks must overlap in staggered brick-laying
seams. If a column of bricks is stacked straight up without overlapping
cross-connections, flag it as Structurally Fragile."

Spatial math:
  Take every vertical clutch edge (supporter top Y ≈ supported bottom Y with
  real stud overlap) and classify it by footprint geometry:

    aligned   — identical XZ extents. The seam of the lower piece sits
                directly under the seam of the upper piece, so the join has
                no lateral bond and the stack can shear along that plane.
    staggered — offset or spanning extents. The upper piece bridges across
                the lower seam, which is what a brick wall does.

  A piece is FRAGILE when it has at least one vertical join and *every* join
  it participates in (above and below) is aligned — a straight column with no
  cross-connection anywhere. A single spanning piece anywhere in the column
  is enough to tie it into the surrounding structure.

  stagger_ratio = staggered / (aligned + staggered), so 1.0 is a fully
  bonded wall and 0.0 is a pure shear column.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from catalog import STUD, get_part  # noqa: E402
from export_io import Brick  # noqa: E402

EPS_Y = 2.0  # LDU — vertical seam tolerance
EPS_XZ = 1.0  # LDU — footprint match tolerance

# A wall this staggered counts as properly bonded.
TARGET_STAGGER_RATIO = 0.5


@dataclass(frozen=True)
class InterlockReport:
    aligned_edges: int
    staggered_edges: int
    fragile_ids: list[int]
    part_count: int

    @property
    def edge_count(self) -> int:
        return self.aligned_edges + self.staggered_edges

    @property
    def stagger_ratio(self) -> float:
        if self.edge_count <= 0:
            return 1.0 if not self.fragile_ids else 0.0
        return self.staggered_edges / self.edge_count

    @property
    def interlocked(self) -> bool:
        return not self.fragile_ids

    @property
    def verdict(self) -> str:
        if self.interlocked:
            return (
                f"PASS - no shear columns "
                f"({100.0 * self.stagger_ratio:.0f}% staggered joins)"
            )
        return (
            f"FAIL - {len(self.fragile_ids)} structurally fragile piece(s) "
            f"in straight columns ({100.0 * self.stagger_ratio:.0f}% staggered)"
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
        xs.append(b.a * lx + b.d * ly + b.g * lz + b.x)
        zs.append(b.c * lx + b.f * ly + b.i * lz + b.z)
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


def _same_footprint(a: Brick, b: Brick) -> bool:
    ax0, ax1, az0, az1 = _xz_aabb(a)
    bx0, bx1, bz0, bz1 = _xz_aabb(b)
    return (
        abs(ax0 - bx0) <= EPS_XZ
        and abs(ax1 - bx1) <= EPS_XZ
        and abs(az0 - bz0) <= EPS_XZ
        and abs(az1 - bz1) <= EPS_XZ
    )


def check_interlock(bricks: list[Brick]) -> InterlockReport:
    n = len(bricks)
    if n == 0:
        return InterlockReport(0, 0, [], 0)

    aligned = 0
    staggered = 0
    # Per piece: does it own any join, and does it own a staggered one?
    has_join: set[int] = set()
    has_stagger: set[int] = set()

    # Bucket by seam plane so only plausible neighbours are compared.
    by_top: dict[int, list[int]] = defaultdict(list)
    for i, b in enumerate(bricks):
        by_top[int(round(_top(b) / EPS_Y))].append(i)

    for i, above in enumerate(bricks):
        key = int(round(_bottom(above) / EPS_Y))
        for offset in (-1, 0, 1):
            for j in by_top.get(key + offset, ()):
                if i == j:
                    continue
                if not _vertical_support(bricks[j], above):
                    continue
                has_join.add(i)
                has_join.add(j)
                if _same_footprint(bricks[j], above):
                    aligned += 1
                else:
                    staggered += 1
                    has_stagger.add(i)
                    has_stagger.add(j)

    fragile = sorted(i for i in has_join if i not in has_stagger)
    return InterlockReport(
        aligned_edges=aligned,
        staggered_edges=staggered,
        fragile_ids=fragile,
        part_count=n,
    )


def format_interlock_report(report: InterlockReport, bricks: list[Brick]) -> str:
    lines = [
        f"VERDICT: {report.verdict}",
        f"  total parts:      {report.part_count}",
        f"  vertical joins:   {report.edge_count}",
        f"  staggered joins:  {report.staggered_edges}",
        f"  aligned joins:    {report.aligned_edges}",
        f"  fragile pieces:   {len(report.fragile_ids)}",
    ]
    if report.fragile_ids:
        lines.append("  fragile samples (first 15):")
        for i in report.fragile_ids[:15]:
            b = bricks[i]
            lines.append(
                f"    [{i}] {b.part_id} @ ({b.x:.0f},{b.y:.0f},{b.z:.0f})"
            )
        if len(report.fragile_ids) > 15:
            lines.append(f"    ... +{len(report.fragile_ids) - 15} more")
    return "\n".join(lines)
