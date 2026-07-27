"""
Phase 5, Step 2 — Overhang / unsupported piece check.

Blueprint anchor: Phase 5 Cantilever & Overhang Check +
"Instruction Feasibility" / gravity during assembly.

Spatial math:
  Each brick has a top at y_origin and bottom at y_origin + height
  (LDraw top-origin, +Y down).

  Support edges:
    1) Vertical: A supports B if A's top ≈ B's bottom AND their XZ
       footprints overlap by at least one stud (tube-on-stud).
    2) Lateral clutch (approx): same layer (tops within eps), footprints
       share a face / touch in XZ (adjacent, not overlapping).

  Grounded bricks = bottom ≈ global minimum bottom.
  A brick is SUPPORTED if reachable from any grounded brick via support
  edges. Everything else is an OVERHANG / floating hazard.
"""

from __future__ import annotations

import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from catalog import STUD, get_part  # noqa: E402
from export_io import Brick  # noqa: E402


EPS_Y = 2.0  # LDU — allow small float / seam error
STUD_TOUCH = STUD * 0.5  # footprints "touch" if gap < half stud


@dataclass(frozen=True)
class OverhangReport:
    grounded_ids: list[int]
    supported_ids: list[int]
    unsupported_ids: list[int]

    @property
    def verdict(self) -> str:
        if self.unsupported_ids:
            return f"FAIL - {len(self.unsupported_ids)} unsupported piece(s)"
        return "PASS - all pieces supported from ground"


def _height(b: Brick) -> float:
    return float(get_part(b.part_id).height_ldu)


def _top(b: Brick) -> float:
    return b.y


def _bottom(b: Brick) -> float:
    return b.y + _height(b)


def _xz_aabb(b: Brick) -> tuple[float, float, float, float]:
    """World XZ AABB of footprint (handles yaw 0/90/180 via corners)."""
    spec = get_part(b.part_id)
    hx = spec.width * STUD / 2.0
    hz = spec.depth * STUD / 2.0
    local = [(-hx, 0.0, -hz), (hx, 0.0, -hz), (hx, 0.0, hz), (-hx, 0.0, hz)]
    xs, zs = [], []
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


def _touching_xz(a: Brick, b: Brick) -> bool:
    """True if footprints touch or overlap in XZ (side clutch)."""
    ax0, ax1, az0, az1 = _xz_aabb(a)
    bx0, bx1, bz0, bz1 = _xz_aabb(b)
    # Expand each by a tiny margin so exact edge-touch counts
    gap_x = max(0.0, max(ax0, bx0) - min(ax1, bx1))
    gap_z = max(0.0, max(az0, bz0) - min(az1, bz1))
    if gap_x == 0.0 and gap_z == 0.0:
        return True  # overlap or exact edge
    # adjacent: touching on one axis, overlapping on the other
    if gap_x <= STUD_TOUCH and gap_z == 0.0:
        return True
    if gap_z <= STUD_TOUCH and gap_x == 0.0:
        return True
    return False


def _same_layer(a: Brick, b: Brick) -> bool:
    return abs(_top(a) - _top(b)) <= EPS_Y


def _vertical_support(below: Brick, above: Brick) -> bool:
    # below.top ≈ above.bottom
    if abs(_top(below) - _bottom(above)) > EPS_Y:
        return False
    # Need meaningful stud overlap (at least ~1/4 stud^2)
    return _overlap_area(below, above) >= (STUD * STUD * 0.25)


def check_overhangs(bricks: list[Brick]) -> OverhangReport:
    n = len(bricks)
    if n == 0:
        return OverhangReport([], [], [])

    bottoms = [_bottom(b) for b in bricks]
    ground_y = min(bottoms)
    grounded = [i for i, by in enumerate(bottoms) if abs(by - ground_y) <= EPS_Y]

    # Adjacency list: support edges undirected for reachability from ground
    adj: dict[int, list[int]] = defaultdict(list)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = bricks[i], bricks[j]
            linked = False
            if _vertical_support(a, b) or _vertical_support(b, a):
                linked = True
            elif _same_layer(a, b) and _touching_xz(a, b):
                linked = True
            if linked:
                adj[i].append(j)
                adj[j].append(i)

    supported: set[int] = set()
    q: deque[int] = deque(grounded)
    supported.update(grounded)
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in supported:
                supported.add(v)
                q.append(v)

    all_ids = set(range(n))
    unsupported = sorted(all_ids - supported)
    return OverhangReport(
        grounded_ids=sorted(grounded),
        supported_ids=sorted(supported),
        unsupported_ids=unsupported,
    )


def format_overhang_report(report: OverhangReport, bricks: list[Brick]) -> str:
    lines = [
        f"VERDICT: {report.verdict}",
        f"  total parts:      {len(bricks)}",
        f"  grounded:         {len(report.grounded_ids)}",
        f"  supported:        {len(report.supported_ids)}",
        f"  unsupported:      {len(report.unsupported_ids)}",
    ]
    if report.unsupported_ids:
        lines.append("  unsupported samples (first 15):")
        for i in report.unsupported_ids[:15]:
            b = bricks[i]
            lines.append(
                f"    [{i}] {b.part_id} @ ({b.x:.0f},{b.y:.0f},{b.z:.0f})"
            )
        if len(report.unsupported_ids) > 15:
            lines.append(f"    ... +{len(report.unsupported_ids) - 15} more")
    return "\n".join(lines)


def colorize_support(bricks: list[Brick], report: OverhangReport) -> list[Brick]:
    """White = supported, red = unsupported (easy to see in Studio)."""
    bad = set(report.unsupported_ids)
    out: list[Brick] = []
    for i, b in enumerate(bricks):
        color = 4 if i in bad else 15  # red vs white
        out.append(
            Brick(
                part_id=b.part_id,
                color=color,
                x=b.x, y=b.y, z=b.z,
                a=b.a, b=b.b, c=b.c, d=b.d, e=b.e, f=b.f, g=b.g, h=b.h, i=b.i,
            )
        )
    return out
