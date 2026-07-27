"""
Phase 5 — Connectivity / detached-sections check.

Blueprint anchor: Phase 2 Connection Engine + Phase 5 structural validation.
Matches what BrickLink Studio's Stability tool reports as "detached sections."

Spatial math (System bricks only):
  Real clutch is vertical stud → tube. Same-layer neighbors do NOT connect
  (no side clutch on standard bricks).

  Brick A supports / clutches Brick B when:
    1) A's top Y ≈ B's bottom Y  (stacked one plate/brick height apart)
    2) At least one of A's stud centers matches one of B's tube centers
       in world XZ (same sites as Phase 2 local_stud_xz).

  Detached sections = connected components of the undirected clutch graph.
  Studio's "N detached sections" ≈ this component count.
"""

from __future__ import annotations

import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase2"))

from catalog import STUD, get_part  # noqa: E402
from connections import local_stud_xz  # noqa: E402
from export_io import Brick  # noqa: E402

EPS_Y = 2.0  # LDU — vertical seam tolerance
EPS_XZ = 1.0  # LDU — stud/tube snap tolerance (~1/20 stud)


# Distinct LDraw colors for component visualization (cycle).
COMPONENT_COLORS = [
    15,  # white — reserved preference for largest
    4,   # red
    14,  # yellow
    1,   # blue
    2,   # green
    25,  # orange
    5,   # dark pink
    71,  # light bluish grey
    72,  # dark bluish grey
    226, # bright yellow
    23,  # purple
    28,  # dark tan
]


@dataclass(frozen=True)
class ConnectivityReport:
    edges: list[tuple[int, int]]
    components: list[list[int]]  # each = sorted brick indices
    component_of: list[int]  # brick index → component id

    @property
    def section_count(self) -> int:
        return len(self.components)

    @property
    def largest_component_id(self) -> int:
        if not self.components:
            return -1
        return max(range(len(self.components)), key=lambda c: len(self.components[c]))

    @property
    def verdict(self) -> str:
        n = self.section_count
        if n <= 1:
            return "PASS - single connected clutch graph"
        return f"FAIL - {n} detached sections (Studio Stability target)"


def _height(b: Brick) -> float:
    return float(get_part(b.part_id).height_ldu)


def _top(b: Brick) -> float:
    return b.y


def _bottom(b: Brick) -> float:
    return b.y + _height(b)


def world_stud_sites(b: Brick) -> list[tuple[float, float]]:
    """Stud/tube XZ sites in world LDU (System: tubes share stud lattice)."""
    spec = get_part(b.part_id)
    out: list[tuple[float, float]] = []
    for lx, lz in local_stud_xz(spec):
        # R @ (lx,0,lz) + t  — LDraw columns (a,b,c), (d,e,f), (g,h,i)
        wx = b.a * lx + b.d * 0.0 + b.g * lz + b.x
        wz = b.c * lx + b.f * 0.0 + b.i * lz + b.z
        out.append((wx, wz))
    return out


def _sites_match(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
    for ax, az in a:
        for bx, bz in b:
            if abs(ax - bx) <= EPS_XZ and abs(az - bz) <= EPS_XZ:
                return True
    return False


def _clutch(below: Brick, above: Brick) -> bool:
    """True if `above` tubes sit on `below` studs (vertical stack)."""
    if abs(_top(below) - _bottom(above)) > EPS_Y:
        return False
    return _sites_match(world_stud_sites(below), world_stud_sites(above))


def find_clutch_edges(bricks: list[Brick]) -> list[tuple[int, int]]:
    """
    Undirected clutch edges (i < j).

    Index studs by (quantized top-Y, stud XZ) so each brick only probes
    overlapping candidates — O(n * studs) instead of O(n²) per layer.
    """
    # Brick i as potential "below": map (top_y_key, qx, qz) → brick indices
    stud_index: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    tops: list[float] = []
    bottoms: list[float] = []
    sites: list[list[tuple[float, float]]] = []

    for i, b in enumerate(bricks):
        t = _top(b)
        bot = _bottom(b)
        tops.append(t)
        bottoms.append(bot)
        st = world_stud_sites(b)
        sites.append(st)
        tkey = int(round(t))
        for sx, sz in st:
            stud_index[(tkey, int(round(sx)), int(round(sz)))].append(i)

    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for j, b in enumerate(bricks):
        # j sits on something whose top ≈ j's bottom
        bkey = int(round(bottoms[j]))
        for sx, sz in sites[j]:
            qx, qz = int(round(sx)), int(round(sz))
            for dy in (-2, -1, 0, 1, 2):
                for i in stud_index.get((bkey + dy, qx, qz), []):
                    if i == j:
                        continue
                    if abs(tops[i] - bottoms[j]) > EPS_Y:
                        continue
                    pair = (i, j) if i < j else (j, i)
                    if pair in seen:
                        continue
                    if _sites_match(sites[i], sites[j]):
                        seen.add(pair)
                        edges.append(pair)
    return edges


def check_connectivity(bricks: list[Brick]) -> ConnectivityReport:
    n = len(bricks)
    if n == 0:
        return ConnectivityReport([], [], [])

    edges = find_clutch_edges(bricks)
    adj: dict[int, list[int]] = defaultdict(list)
    for i, j in edges:
        adj[i].append(j)
        adj[j].append(i)

    component_of = [-1] * n
    components: list[list[int]] = []
    for start in range(n):
        if component_of[start] >= 0:
            continue
        cid = len(components)
        members: list[int] = []
        q: deque[int] = deque([start])
        component_of[start] = cid
        while q:
            u = q.popleft()
            members.append(u)
            for v in adj[u]:
                if component_of[v] < 0:
                    component_of[v] = cid
                    q.append(v)
        components.append(sorted(members))

    return ConnectivityReport(
        edges=edges,
        components=components,
        component_of=component_of,
    )


def format_connectivity_report(report: ConnectivityReport, bricks: list[Brick]) -> str:
    sizes = sorted((len(c) for c in report.components), reverse=True)
    lines = [
        f"VERDICT: {report.verdict}",
        f"  total parts:         {len(bricks)}",
        f"  clutch edges:        {len(report.edges)}",
        f"  detached sections:   {report.section_count}",
        f"  largest section:     {sizes[0] if sizes else 0} parts",
        f"  singleton sections:  {sum(1 for s in sizes if s == 1)}",
    ]
    if sizes:
        top = ", ".join(str(s) for s in sizes[:12])
        more = f" ... +{len(sizes) - 12} more" if len(sizes) > 12 else ""
        lines.append(f"  size histogram (desc): {top}{more}")
    return "\n".join(lines)


def colorize_by_component(
    bricks: list[Brick],
    report: ConnectivityReport,
) -> list[Brick]:
    """
    Paint each detached section a different color.
    Largest section stays white so islands read as colored floaters.
    """
    largest = report.largest_component_id
    # Map component id → palette slot (largest → white / index 0)
    other_ids = [c for c in range(len(report.components)) if c != largest]
    color_of: dict[int, int] = {largest: COMPONENT_COLORS[0]}
    for k, cid in enumerate(other_ids):
        color_of[cid] = COMPONENT_COLORS[1 + (k % (len(COMPONENT_COLORS) - 1))]

    out: list[Brick] = []
    for i, b in enumerate(bricks):
        cid = report.component_of[i]
        color = color_of.get(cid, 4)
        out.append(
            Brick(
                part_id=b.part_id,
                color=color,
                x=b.x, y=b.y, z=b.z,
                a=b.a, b=b.b, c=b.c, d=b.d, e=b.e, f=b.f, g=b.g, h=b.h, i=b.i,
            )
        )
    return out
