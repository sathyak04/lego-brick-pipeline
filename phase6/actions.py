"""
Phase 6 — fix actions the release agent can attempt.

Each action takes a brick list and returns (new_bricks, parts_added).
Actions are pure geometry — the hill-climber decides keep vs revert.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase2"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5"))

from catalog import BRICK_H, PLATE_H, STUD, get_part  # noqa: E402
from connections import local_stud_xz  # noqa: E402
from export_io import Brick  # noqa: E402
from brick_collision import CollisionWorld, count_collisions  # noqa: E402
from build_order import check_build_order  # noqa: E402
from connectivity import check_connectivity  # noqa: E402
from stabilize import add_balance_base  # noqa: E402

FixFn = Callable[..., tuple[list[Brick], int]]

EPS_Y = 2.0


def _height(b: Brick) -> float:
    return float(get_part(b.part_id).height_ldu)


def _bottom(b: Brick) -> float:
    return b.y + _height(b)


def _axis_part(part_id: str, color: int, x: float, y: float, z: float) -> Brick:
    return Brick(
        part_id=part_id,
        color=color,
        x=x,
        y=y,
        z=z,
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


def _world_studs(b: Brick) -> list[tuple[float, float]]:
    """Stud/tube XZ sites in world LDU (same lattice connectivity uses)."""
    spec = get_part(b.part_id)
    out: list[tuple[float, float]] = []
    for lx, lz in local_stud_xz(spec):
        wx = b.a * lx + b.g * lz + b.x
        wz = b.c * lx + b.i * lz + b.z
        out.append((wx, wz))
    return out


def _column_under(
    *,
    cx: float,
    cz: float,
    start_top: float,
    ground_y: float,
    color: int,
    world: CollisionWorld,
) -> list[Brick] | None:
    """Stack 1x1 bricks (then plates) from start_top down to ground_y."""
    column: list[Brick] = []
    top_y = start_top

    if abs(top_y - ground_y) <= EPS_Y or top_y >= ground_y - EPS_Y:
        return []

    while top_y < ground_y - EPS_Y:
        remaining = ground_y - top_y
        if remaining >= BRICK_H - EPS_Y:
            part_id = "3005.dat"
        elif remaining >= PLATE_H - EPS_Y:
            part_id = "3024.dat"
        else:
            return None

        piece = _axis_part(part_id, color, cx, top_y, cz)
        if world.collides(piece):
            return None
        if _bottom(piece) > ground_y + EPS_Y:
            return None
        column.append(piece)
        top_y = _bottom(piece)
        if len(column) > 40:
            return None

    return column


def support_blocked_pieces(
    bricks: list[Brick],
    *,
    max_targets: int = 4,
    color: int = 72,
) -> tuple[list[Brick], int]:
    """Drop stud-aligned 1x1 columns under mid-air pieces.

    Columns must land on real stud sites so they clutch (Studio sections
    stay green). Rejects any candidate that raises section count or
    collisions.
    """
    start_sec = check_connectivity(bricks).section_count
    if check_build_order(bricks).buildable:
        return list(bricks), 0

    ground_y = max(_bottom(b) for b in bricks)
    out = list(bricks)
    world = CollisionWorld(out)
    added = 0
    targets = 0
    skipped: set[tuple[float, float, float]] = set()

    while targets < max_targets:
        report = check_build_order(out)
        if report.buildable or not report.blocked_ids:
            break

        candidates = sorted(report.blocked_ids, key=lambda i: -_bottom(out[i]))
        progressed = False
        for bi in candidates:
            target = out[bi]
            key = (round(target.x, 1), round(target.y, 1), round(target.z, 1))
            if key in skipped:
                continue

            studs = _world_studs(target)
            if not studs:
                skipped.add(key)
                continue

            # Prefer the stud closest to the brick origin (stable, centered).
            studs = sorted(studs, key=lambda s: (s[0] - target.x) ** 2 + (s[1] - target.z) ** 2)
            placed_column: list[Brick] | None = None
            for cx, cz in studs:
                column = _column_under(
                    cx=cx,
                    cz=cz,
                    start_top=_bottom(target),
                    ground_y=ground_y,
                    color=color,
                    world=world,
                )
                if not column:
                    continue
                trial = out + column
                if count_collisions(trial) > 0:
                    continue
                sec = check_connectivity(trial).section_count
                if sec > start_sec:
                    continue
                before_n = len(report.blocked_ids)
                after = check_build_order(trial)
                if len(after.blocked_ids) >= before_n:
                    continue
                placed_column = column
                break

            if placed_column is None:
                skipped.add(key)
                continue

            for piece in placed_column:
                world.add(piece)
            out = out + placed_column
            added += len(placed_column)
            targets += 1
            progressed = True
            break

        if not progressed:
            break

    return out, added


def widen_balance_base(
    bricks: list[Brick],
    *,
    plate_color: int = 72,
) -> tuple[list[Brick], int]:
    """Wrap stabilize.add_balance_base as a Phase 6 action."""
    new_bricks, _bal, n = add_balance_base(bricks, plate_color=plate_color)
    return new_bricks, n


ACTIONS: dict[str, FixFn] = {
    "support_blocked_pieces": support_blocked_pieces,
    "add_balance_base": widen_balance_base,
}
