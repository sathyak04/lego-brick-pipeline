"""
Phase 5, Step 1 — Balance / tipping check.

Blueprint anchor: Phase 5 Balance Engine + Release Standard
"Gravitational Balance & Stability".

Spatial math (LDraw: -Y up, gravity along +Y):
  1. Mass of a part ≈ footprint_area * height  (LDU^3), uniform density.
  2. Center of mass:
       CoM = sum(m_i * center_i) / sum(m_i)
     Part center = origin + (0, height/2, 0) in part space, then world pose.
     (Top-origin parts: geometric center is half-height toward +Y / down.)
  3. Footprint = XZ outline of parts whose BOTTOM sits on the ground
     (bottom y ≈ max bottom among all parts, within epsilon — +Y is down).
  4. Drop gravity from CoM straight "down" onto XZ → point (CoM_x, CoM_z).
  5. PASS if that point lies inside the footprint polygon with a stud-margin
     from the boundary; else FAIL as "Tipping Hazard".
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from catalog import STUD, get_part  # noqa: E402
from export_io import Brick  # noqa: E402


@dataclass(frozen=True)
class BalanceReport:
    com: tuple[float, float, float]
    footprint_points: list[tuple[float, float]]  # XZ polygon (CCW)
    support_xz: tuple[float, float]  # CoM projected on ground
    inside: bool
    edge_margin_ldu: float
    min_margin_ldu: float
    tip_hazard: bool
    total_mass: float
    ground_parts: int

    @property
    def verdict(self) -> str:
        if self.tip_hazard:
            return "FAIL - Tipping Hazard"
        return "PASS - balanced"


def _part_mass_and_center(brick: Brick) -> tuple[float, tuple[float, float, float]]:
    spec = get_part(brick.part_id)
    # Footprint in local part space before rot: use catalog width/depth
    # Volume ~ w * d * h in stud/brick units → scale to LDU^3
    w = spec.width * STUD
    d = spec.depth * STUD
    h = float(spec.height_ldu)
    mass = w * d * h

    # Local geometric center relative to top-origin: (0, +h/2, 0)
    # Apply rotation then translation (same as Transform.apply).
    lx, ly, lz = 0.0, h / 2.0, 0.0
    # R columns (a,b,c), (d,e,f), (g,h,i)
    wx = brick.a * lx + brick.d * ly + brick.g * lz + brick.x
    wy = brick.b * lx + brick.e * ly + brick.h * lz + brick.y
    wz = brick.c * lx + brick.f * ly + brick.i * lz + brick.z
    return mass, (wx, wy, wz)


def _part_bottom_y(brick: Brick) -> float:
    spec = get_part(brick.part_id)
    # Top at origin y (approx for yaw-only); bottom = y + height (+Y down)
    # With yaw about Y, height axis still aligns with world Y.
    return brick.y + float(spec.height_ldu)


def _footprint_corners(brick: Brick) -> list[tuple[float, float]]:
    """World XZ corners of the part footprint AABB (yaw 0/90/180 friendly)."""
    spec = get_part(brick.part_id)
    # Local footprint corners at y=0 (top plane), then rotate+translate
    hx = spec.width * STUD / 2.0
    hz = spec.depth * STUD / 2.0
    local = [(-hx, 0.0, -hz), (hx, 0.0, -hz), (hx, 0.0, hz), (-hx, 0.0, hz)]
    out: list[tuple[float, float]] = []
    for lx, ly, lz in local:
        wx = brick.a * lx + brick.d * ly + brick.g * lz + brick.x
        wz = brick.c * lx + brick.f * ly + brick.i * lz + brick.z
        out.append((wx, wz))
    return out


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Monotone chain convex hull, CCW."""
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _point_in_poly(x: float, z: float, poly: list[tuple[float, float]]) -> bool:
    """Ray casting in XZ."""
    if len(poly) < 3:
        return False
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, zi = poly[i]
        xj, zj = poly[j]
        if ((zi > z) != (zj > z)) and (
            x < (xj - xi) * (z - zi) / (zj - zi + 1e-15) + xi
        ):
            inside = not inside
        j = i
    return inside


def _distance_to_edges(x: float, z: float, poly: list[tuple[float, float]]) -> float:
    """Min distance from point to polygon boundary."""
    if len(poly) < 2:
        return 0.0
    best = float("inf")
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        dx, dz = x2 - x1, z2 - z1
        if abs(dx) < 1e-12 and abs(dz) < 1e-12:
            dist = math.hypot(x - x1, z - z1)
        else:
            t = max(0.0, min(1.0, ((x - x1) * dx + (z - z1) * dz) / (dx * dx + dz * dz)))
            px, pz = x1 + t * dx, z1 + t * dz
            dist = math.hypot(x - px, z - pz)
        best = min(best, dist)
    return best


def check_balance(
    bricks: list[Brick],
    *,
    min_margin_studs: float = 1.0,
) -> BalanceReport:
    if not bricks:
        return BalanceReport(
            com=(0, 0, 0),
            footprint_points=[],
            support_xz=(0, 0),
            inside=False,
            edge_margin_ldu=0.0,
            min_margin_ldu=min_margin_studs * STUD,
            tip_hazard=True,
            total_mass=0.0,
            ground_parts=0,
        )

    bottoms = [_part_bottom_y(b) for b in bricks]
    # +Y is down: the ground plane is the *largest* bottom Y (furthest down).
    ground_y = max(bottoms)
    eps = 1.0  # LDU tolerance for "on ground"

    ground: list[Brick] = []
    corners: list[tuple[float, float]] = []
    for b, by in zip(bricks, bottoms):
        if abs(by - ground_y) <= eps:
            ground.append(b)
            corners.extend(_footprint_corners(b))

    hull = _convex_hull(corners) if corners else []

    total = 0.0
    cx = cy = cz = 0.0
    for b in bricks:
        m, (x, y, z) = _part_mass_and_center(b)
        total += m
        cx += m * x
        cy += m * y
        cz += m * z
    com = (cx / total, cy / total, cz / total) if total > 0 else (0.0, 0.0, 0.0)
    support = (com[0], com[2])

    inside = _point_in_poly(support[0], support[1], hull) if hull else False
    margin = _distance_to_edges(support[0], support[1], hull) if inside else 0.0
    # If outside, margin = 0 and tip hazard
    min_margin = min_margin_studs * STUD
    tip = (not inside) or (margin < min_margin)

    return BalanceReport(
        com=com,
        footprint_points=hull,
        support_xz=support,
        inside=inside,
        edge_margin_ldu=margin,
        min_margin_ldu=min_margin,
        tip_hazard=tip,
        total_mass=total,
        ground_parts=len(ground),
    )


def format_report(report: BalanceReport) -> str:
    lines = [
        f"VERDICT: {report.verdict}",
        f"  ground parts:     {report.ground_parts}",
        f"  CoM LDU:          ({report.com[0]:.1f}, {report.com[1]:.1f}, {report.com[2]:.1f})",
        f"  support XZ:       ({report.support_xz[0]:.1f}, {report.support_xz[1]:.1f})",
        f"  inside footprint: {report.inside}",
        f"  edge margin:      {report.edge_margin_ldu:.1f} LDU "
        f"(need >= {report.min_margin_ldu:.1f})",
        f"  footprint verts:  {len(report.footprint_points)}",
    ]
    return "\n".join(lines)
