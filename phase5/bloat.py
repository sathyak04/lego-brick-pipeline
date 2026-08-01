"""
Phase 5 — Part-count bloat audit.

Blueprint anchor: Release Standard "Part Count Bloat Control" —
"If two adjacent 1x2 bricks can be replaced by a single 1x4 brick without
changing the aesthetic, the engine MUST merge them."

Phase 4 already staggers and merges at generation time; this module audits
the *result*, so the agent can measure leftover cost bloat instead of
trusting the packer.

Spatial math:
  1. A merge candidate pair must be interchangeable with one real part:
     same layer (equal top Y), same colour, same kind, same height.
  2. Their world XZ footprints must be flush along one axis — equal extent
     on the other axis and zero gap on the shared edge.
  3. The combined footprint (in studs) must exist in the catalog as a
     rectangular part of the same kind, in either orientation.
  4. Each brick may be claimed by at most one merge, so `wasted_parts`
     counts real removable pieces rather than overlapping possibilities.

Aesthetics are preserved by construction: identical colour, identical kind,
identical occupied studs. Interlocking is *not* considered here — a merge
that would erase a staggered seam is still reported, and the interlock
audit is what keeps that trade-off visible.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from catalog import CATALOG, STUD, get_part  # noqa: E402
from export_io import Brick  # noqa: E402

EPS_Y = 2.0  # LDU — layer / height tolerance
EPS_XZ = 1.0  # LDU — flush-edge tolerance


@dataclass(frozen=True)
class MergePair:
    a: int
    b: int
    replacement: str
    detail: str


@dataclass(frozen=True)
class BloatReport:
    merge_pairs: list[MergePair]
    part_count: int

    @property
    def wasted_parts(self) -> int:
        """Pieces removable by merging — one per claimed pair."""
        return len(self.merge_pairs)

    @property
    def lean(self) -> bool:
        return not self.merge_pairs

    @property
    def bloat_ratio(self) -> float:
        if self.part_count <= 0:
            return 0.0
        return self.wasted_parts / self.part_count

    @property
    def verdict(self) -> str:
        if self.lean:
            return "PASS - no adjacent pairs replaceable by a single part"
        return (
            f"FAIL - {self.wasted_parts} part(s) removable by merging "
            f"({100.0 * self.bloat_ratio:.1f}% of the set)"
        )


def _footprint_by_kind() -> dict[tuple[str, int, int], str]:
    """(kind, w, d) -> part_id for rectangular catalog parts."""
    out: dict[tuple[str, int, int], str] = {}
    for spec in CATALOG.values():
        if not spec.is_rectangular():
            continue
        out.setdefault((spec.kind, spec.width, spec.depth), spec.part_id)
    return out


_FOOTPRINTS = _footprint_by_kind()


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


def _studs(length_ldu: float) -> int:
    return int(round(length_ldu / STUD))


def _lookup(kind: str, w: int, d: int) -> str | None:
    """Catalog part with this stud footprint, either orientation."""
    return _FOOTPRINTS.get((kind, w, d)) or _FOOTPRINTS.get((kind, d, w))


def _merge_candidate(a: Brick, b: Brick) -> tuple[str, str] | None:
    spec_a, spec_b = get_part(a.part_id), get_part(b.part_id)
    if a.color != b.color or spec_a.kind != spec_b.kind:
        return None
    if spec_a.height_ldu != spec_b.height_ldu:
        return None
    if abs(a.y - b.y) > EPS_Y:
        return None
    if not (spec_a.is_rectangular() and spec_b.is_rectangular()):
        return None

    ax0, ax1, az0, az1 = _xz_aabb(a)
    bx0, bx1, bz0, bz1 = _xz_aabb(b)

    flush_x = (
        abs(az0 - bz0) <= EPS_XZ
        and abs(az1 - bz1) <= EPS_XZ
        and (abs(ax1 - bx0) <= EPS_XZ or abs(bx1 - ax0) <= EPS_XZ)
    )
    flush_z = (
        abs(ax0 - bx0) <= EPS_XZ
        and abs(ax1 - bx1) <= EPS_XZ
        and (abs(az1 - bz0) <= EPS_XZ or abs(bz1 - az0) <= EPS_XZ)
    )
    if not (flush_x or flush_z):
        return None

    w = _studs(max(ax1, bx1) - min(ax0, bx0))
    d = _studs(max(az1, bz1) - min(az0, bz0))
    part_id = _lookup(spec_a.kind, w, d)
    if part_id is None:
        return None
    return part_id, f"{spec_a.name} + {spec_b.name} -> {w}x{d}"


def check_bloat(bricks: list[Brick]) -> BloatReport:
    n = len(bricks)
    claimed: set[int] = set()
    pairs: list[MergePair] = []

    # Bucket by layer so large models don't pay the full O(n^2) pair scan.
    layers: dict[int, list[int]] = {}
    for i, b in enumerate(bricks):
        layers.setdefault(int(round(b.y / EPS_Y)), []).append(i)

    for _key, idxs in sorted(layers.items()):
        for pos, i in enumerate(idxs):
            if i in claimed:
                continue
            for j in idxs[pos + 1 :]:
                if j in claimed:
                    continue
                found = _merge_candidate(bricks[i], bricks[j])
                if found is None:
                    continue
                part_id, detail = found
                pairs.append(MergePair(a=i, b=j, replacement=part_id, detail=detail))
                claimed.add(i)
                claimed.add(j)
                break

    return BloatReport(merge_pairs=pairs, part_count=n)


def format_bloat_report(report: BloatReport, bricks: list[Brick]) -> str:
    lines = [
        f"VERDICT: {report.verdict}",
        f"  total parts:      {report.part_count}",
        f"  removable parts:  {report.wasted_parts}",
    ]
    if report.merge_pairs:
        lines.append("  merge samples (first 15):")
        for pair in report.merge_pairs[:15]:
            b = bricks[pair.a]
            lines.append(
                f"    [{pair.a}+{pair.b}] {pair.detail} = {pair.replacement} "
                f"@ ({b.x:.0f},{b.y:.0f},{b.z:.0f})"
            )
        if len(report.merge_pairs) > 15:
            lines.append(f"    ... +{len(report.merge_pairs) - 15} more")
    return "\n".join(lines)
