"""
Widen the ground footprint when a hollow model tips.

Adds a single large System plate under existing ground bricks so the CoM
projection sits inside the footprint with margin. Keeps hollow interiors
unchanged — only adds a base under the lowest layer.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import PLATE_H, STUD, get_part  # noqa: E402
from export_io import Brick  # noqa: E402
from balance import (  # noqa: E402
    BalanceReport,
    _footprint_corners,
    _part_bottom_y,
    check_balance,
)
from brick_collision import count_collisions  # noqa: E402
from connectivity import check_connectivity  # noqa: E402

# Largest-first base plates (part_id, w, d)
_BASE_PLATES: list[tuple[str, int, int]] = [
    ("41539.dat", 8, 8),
    ("3036.dat", 8, 6),
    ("3958.dat", 6, 6),
    ("3035.dat", 8, 4),
    ("3032.dat", 6, 4),
    ("3031.dat", 4, 4),
    ("3034.dat", 8, 2),
    ("3795.dat", 6, 2),
    ("3020.dat", 4, 2),
]


def _make_plate(
    part_id: str,
    color: int,
    cx: float,
    cz: float,
    top_y: float,
) -> Brick:
    return Brick(
        part_id=part_id,
        color=color,
        x=cx,
        y=top_y,
        z=cz,
        a=1.0,
        b=0.0,
        c=0.0,
        d=0.0,
        e=1.0,
        f=0.0,
        g=0.0,
        h=0.0,
        i=1.0,
    )


def _plate_covers(
    part_id: str,
    cx: float,
    cz: float,
    points: list[tuple[float, float]],
    margin_ldu: float,
) -> bool:
    spec = get_part(part_id)
    hx = spec.width * STUD / 2.0 - margin_ldu
    hz = spec.depth * STUD / 2.0 - margin_ldu
    if hx <= 0 or hz <= 0:
        return False
    for x, z in points:
        if abs(x - cx) > hx or abs(z - cz) > hz:
            return False
    return True


def _snap_plate_center(cx: float, cz: float, w: int, d: int) -> tuple[float, float]:
    """Snap plate center so studs land on the integer stud lattice."""
    ix = int(round(cx / STUD - w / 2.0))
    iz = int(round(cz / STUD - d / 2.0))
    return (ix + w / 2.0) * STUD, (iz + d / 2.0) * STUD


def add_balance_base(
    bricks: list[Brick],
    *,
    plate_color: int = 72,
    min_margin_studs: float = 0.5,
) -> tuple[list[Brick], BalanceReport, int]:
    """If tipping, try one under-plate base. Returns (bricks, balance, n_added)."""
    before = check_balance(bricks, min_margin_studs=min_margin_studs)
    if not before.tip_hazard:
        return bricks, before, 0
    if not bricks:
        return bricks, before, 0

    bottoms = [_part_bottom_y(b) for b in bricks]
    # +Y is down: ground plane = max bottom Y.
    ground_y = max(bottoms)
    eps = 1.0
    ground = [b for b, by in zip(bricks, bottoms) if abs(by - ground_y) <= eps]
    if not ground:
        return bricks, before, 0

    # Must cover current ground footprints + CoM with margin.
    pts: list[tuple[float, float]] = [before.support_xz]
    for b in ground:
        pts.extend(_footprint_corners(b))
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    raw_centers = [
        (0.5 * (min(xs) + max(xs)), 0.5 * (min(zs) + max(zs))),
        before.support_xz,
    ]

    margin = min_margin_studs * STUD
    # Plate top flush under current ground bottoms
    top_y = ground_y
    before_sec = check_connectivity(bricks).section_count
    before_cols = count_collisions(bricks)

    for part_id, w, d in _BASE_PLATES:
        for raw in raw_centers:
            cx, cz = _snap_plate_center(raw[0], raw[1], w, d)
            if not _plate_covers(part_id, cx, cz, pts, margin):
                continue
            plate = _make_plate(part_id, plate_color, cx, cz, top_y)
            trial = list(bricks) + [plate]
            cols = count_collisions(trial)
            if cols > before_cols:
                continue
            sec = check_connectivity(trial).section_count
            if sec > before_sec:
                continue
            after = check_balance(trial, min_margin_studs=min_margin_studs)
            if after.tip_hazard:
                continue
            return trial, after, 1

    # Fallback: largest plate snapped on CoM — keep only if balance + 1-section hold
    part_id, w, d = _BASE_PLATES[0]
    cx, cz = _snap_plate_center(before.support_xz[0], before.support_xz[1], w, d)
    plate = _make_plate(part_id, plate_color, cx, cz, top_y)
    trial = list(bricks) + [plate]
    if count_collisions(trial) <= before_cols:
        sec = check_connectivity(trial).section_count
        if sec <= before_sec:
            after = check_balance(trial, min_margin_studs=min_margin_studs)
            if not after.tip_hazard:
                return trial, after, 1

    return bricks, before, 0
