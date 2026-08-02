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


def _merged_brick(a: Brick, b: Brick, part_id: str) -> Brick | None:
    """Build a single part covering the combined XZ footprint of a and b."""
    from bloat import _xz_aabb, _studs  # local helpers

    ax0, ax1, az0, az1 = _xz_aabb(a)
    bx0, bx1, bz0, bz1 = _xz_aabb(b)
    x0, x1 = min(ax0, bx0), max(ax1, bx1)
    z0, z1 = min(az0, bz0), max(az1, bz1)
    w, d = _studs(x1 - x0), _studs(z1 - z0)
    spec = get_part(part_id)
    from catalog import IDENTITY, YAW_90

    if spec.width == w and spec.depth == d:
        rot = IDENTITY
    elif spec.width == d and spec.depth == w:
        rot = YAW_90
    else:
        return None
    cx, cz = 0.5 * (x0 + x1), 0.5 * (z0 + z1)
    return Brick(
        part_id=part_id,
        color=a.color,
        x=cx,
        y=a.y,
        z=cz,
        a=rot[0],
        b=rot[1],
        c=rot[2],
        d=rot[3],
        e=rot[4],
        f=rot[5],
        g=rot[6],
        h=rot[7],
        i=rot[8],
    )


def merge_bloat(
    bricks: list[Brick],
    *,
    max_merges: int = 24,
) -> tuple[list[Brick], int]:
    """Replace adjacent same-layer pairs with one catalog part (cost bloat)."""
    from bloat import check_bloat

    report = check_bloat(bricks)
    if report.lean:
        return list(bricks), 0

    start_sec = check_connectivity(bricks).section_count
    remove: set[int] = set()
    additions: list[Brick] = []
    merges = 0
    for pair in report.merge_pairs:
        if merges >= max_merges:
            break
        if pair.a in remove or pair.b in remove:
            continue
        merged = _merged_brick(bricks[pair.a], bricks[pair.b], pair.replacement)
        if merged is None:
            continue
        remove.add(pair.a)
        remove.add(pair.b)
        additions.append(merged)
        merges += 1

    if merges <= 0:
        return list(bricks), 0

    out = [b for i, b in enumerate(bricks) if i not in remove] + additions
    if count_collisions(out) > 0:
        return list(bricks), 0
    if check_connectivity(out).section_count > start_sec:
        return list(bricks), 0
    return out, merges


def stagger_seams(
    bricks: list[Brick],
    *,
    max_shifts: int = 12,
) -> tuple[list[Brick], int]:
    """Shift fragile aligned-stack pieces by one stud to break shear columns."""
    from interlock import check_interlock

    report = check_interlock(bricks)
    if report.interlocked or not report.fragile_ids:
        return list(bricks), 0

    start_sec = check_connectivity(bricks).section_count
    start_fragile = len(report.fragile_ids)
    out = list(bricks)
    shifts = 0

    for fi in list(report.fragile_ids):
        if shifts >= max_shifts:
            break
        if fi >= len(out):
            continue
        brick = out[fi]
        # Prefer shifting along the longer footprint axis.
        spec = get_part(brick.part_id)
        deltas = [(STUD, 0.0), (-STUD, 0.0), (0.0, STUD), (0.0, -STUD)]
        if spec.depth > spec.width:
            deltas = [(0.0, STUD), (0.0, -STUD), (STUD, 0.0), (-STUD, 0.0)]

        best: Brick | None = None
        for dx, dz in deltas:
            trial_brick = Brick(
                part_id=brick.part_id,
                color=brick.color,
                x=brick.x + dx,
                y=brick.y,
                z=brick.z + dz,
                a=brick.a,
                b=brick.b,
                c=brick.c,
                d=brick.d,
                e=brick.e,
                f=brick.f,
                g=brick.g,
                h=brick.h,
                i=brick.i,
            )
            trial = list(out)
            trial[fi] = trial_brick
            if count_collisions(trial) > 0:
                continue
            if check_connectivity(trial).section_count > start_sec:
                continue
            after = check_interlock(trial)
            if len(after.fragile_ids) >= start_fragile:
                continue
            # Must remain placeable enough — don't create new mid-air piles.
            before_blocked = len(check_build_order(out).blocked_ids)
            after_blocked = len(check_build_order(trial).blocked_ids)
            if after_blocked > before_blocked + 2:
                continue
            best = trial_brick
            start_fragile = len(after.fragile_ids)
            break
        if best is None:
            continue
        out[fi] = best
        shifts += 1

    return out, shifts


def strengthen_clutch(
    bricks: list[Brick],
    *,
    max_plates: int = 8,
    color: int = 72,
) -> tuple[list[Brick], int]:
    """Lay 1x2 plates across adjacent same-layer studs that only clutch 1-wide.

    Targets weak vertical joins indirectly: a plate spanning two neighbour
    uppers bonds them and adds multi-stud clutch into the layer below when
    both sit on the same support.
    """
    from connectivity import clutch_strength

    conn = check_connectivity(bricks)
    strength = clutch_strength(bricks, conn)
    if strength.weak_edges <= 0:
        return list(bricks), 0

    start_sec = conn.section_count
    world = CollisionWorld(bricks)
    out = list(bricks)
    added = 0

    # Weak edge endpoints that are "above" in a vertical join.
    weak_uppers: list[int] = []
    for (i, j), ov in zip(conn.edges, strength.overlaps):
        if ov != 1:
            continue
        bi, bj = bricks[i], bricks[j]
        # Upper = smaller top Y (higher in air, +Y down)
        upper = i if bi.y < bj.y else j
        weak_uppers.append(upper)

    # Pair nearby weak uppers on the same layer one stud apart.
    seen: set[tuple[int, int]] = set()
    for a_idx in weak_uppers:
        if added >= max_plates:
            break
        a = out[a_idx]
        for b_idx in weak_uppers:
            if a_idx >= b_idx:
                continue
            key = (a_idx, b_idx)
            if key in seen:
                continue
            seen.add(key)
            b = out[b_idx]
            if abs(a.y - b.y) > EPS_Y:
                continue
            dx = abs(a.x - b.x)
            dz = abs(a.z - b.z)
            # Exactly one stud apart on one axis, aligned on the other.
            if abs(dx - STUD) <= 1.0 and abs(dz) <= 1.0:
                cx, cz = 0.5 * (a.x + b.x), a.z
                # Plate sits on top of both (top origin = their top)
                plate = _axis_part("3023.dat", color, cx, a.y - PLATE_H, cz)
                # 3023 is 1x2 along X by default — good for dx=STUD
            elif abs(dz - STUD) <= 1.0 and abs(dx) <= 1.0:
                cx, cz = a.x, 0.5 * (a.z + b.z)
                from catalog import YAW_90

                plate = Brick(
                    part_id="3023.dat",
                    color=color,
                    x=cx,
                    y=a.y - PLATE_H,
                    z=cz,
                    a=YAW_90[0],
                    b=YAW_90[1],
                    c=YAW_90[2],
                    d=YAW_90[3],
                    e=YAW_90[4],
                    f=YAW_90[5],
                    g=YAW_90[6],
                    h=YAW_90[7],
                    i=YAW_90[8],
                )
            else:
                continue
            if world.collides(plate):
                continue
            trial = out + [plate]
            if count_collisions(trial) > 0:
                continue
            if check_connectivity(trial).section_count > start_sec:
                continue
            new_strength = clutch_strength(trial, check_connectivity(trial))
            if new_strength.mean_overlap < strength.mean_overlap - 1e-6:
                continue
            if (
                new_strength.weak_ratio >= strength.weak_ratio
                and new_strength.mean_overlap <= strength.mean_overlap + 1e-6
            ):
                continue
            world.add(plate)
            out.append(plate)
            added += 1
            strength = new_strength
            break

    return out, added


ACTIONS: dict[str, FixFn] = {
    "support_blocked_pieces": support_blocked_pieces,
    "add_balance_base": widen_balance_base,
    "merge_bloat": merge_bloat,
    "stagger_seams": stagger_seams,
    "strengthen_clutch": strengthen_clutch,
}
