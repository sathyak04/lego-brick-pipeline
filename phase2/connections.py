"""
Phase 2, Step 3 — Stud / tube connection validation.

Blueprint anchor: Phase 2 Connection Engine + Release Standard
"Strictly Legal Builds" — bricks must sit on real studs, not just
avoid AABB overlaps.

Spatial math:
  A WxD part has stud centers in local XZ (LDraw origin = top center):

    x_i = (i - (W - 1) / 2) * 20     i = 0 .. W-1
    z_j = (j - (D - 1) / 2) * 20     j = 0 .. D-1

  Examples:
    1x1 → (0, 0)           origin ON a stud
    2x2 → (±10, ±10)       origin BETWEEN studs
    2x4 → (±10/±30, ±10)

  Bottom tubes line up with those same XZ sites (System bricks).
  For a parent→child stack edge, every child tube XZ must match a
  parent stud XZ (within epsilon). Vertical stacking is assumed via
  stack_on_studs; this check only validates the stud grid footprint.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from catalog import STUD, PartSpec, get_part  # noqa: E402
from scene import BrickNode, SceneGraph  # noqa: E402
from transform import Transform  # noqa: E402

# Half a stud is 10 LDU; we allow a tiny float tolerance only.
EPS = 0.05


def local_stud_xz(spec: PartSpec) -> list[tuple[float, float]]:
    """Stud centers in part-local XZ (LDU). Uses catalog override when set."""
    if spec.studs is not None:
        return [(sx * STUD, sz * STUD) for sx, sz in spec.studs]

    sites: list[tuple[float, float]] = []
    for i in range(spec.width):
        for j in range(spec.depth):
            lx = (i - (spec.width - 1) / 2.0) * STUD
            lz = (j - (spec.depth - 1) / 2.0) * STUD
            sites.append((lx, lz))
    return sites


def world_stud_xz(spec: PartSpec, pose: Transform) -> list[tuple[float, float]]:
    """Project local stud sites into world XZ via the node pose."""
    out: list[tuple[float, float]] = []
    for lx, lz in local_stud_xz(spec):
        wx, _wy, wz = pose.apply(lx, 0.0, lz)
        out.append((wx, wz))
    return out


def _near(ax: float, az: float, bx: float, bz: float) -> bool:
    return abs(ax - bx) <= EPS and abs(az - bz) <= EPS


@dataclass(frozen=True)
class StudFault:
    child_id: str
    parent_id: str
    child_part: str
    parent_part: str
    tube_world: tuple[float, float]
    detail: str


def find_stud_faults(scene: SceneGraph) -> list[StudFault]:
    """
    For every parent→child edge, require each child tube to sit on a parent stud.
    Roots are skipped (they rest on the ground plane / baseplate).
    """
    faults: list[StudFault] = []
    for child in scene.iter_nodes():
        parent = child.parent
        if parent is None:
            continue

        child_spec = get_part(child.part_id)
        parent_spec = get_part(parent.part_id)
        child_pose = scene.world_pose(child)
        parent_pose = scene.world_pose(parent)

        tubes = world_stud_xz(child_spec, child_pose)
        studs = world_stud_xz(parent_spec, parent_pose)

        for tx, tz in tubes:
            if any(_near(tx, tz, sx, sz) for sx, sz in studs):
                continue
            faults.append(
                StudFault(
                    child_id=child.id,
                    parent_id=parent.id,
                    child_part=child.part_id,
                    parent_part=parent.part_id,
                    tube_world=(tx, tz),
                    detail=(
                        f"tube at world XZ=({tx:.1f}, {tz:.1f}) is not on any "
                        f"stud of '{parent.id}' ({parent_spec.name})"
                    ),
                )
            )
    return faults


def report_stud_faults(scene: SceneGraph, title: str = "") -> str:
    faults = find_stud_faults(scene)
    header = f"=== {title} ===\n" if title else ""
    if not faults:
        return header + "STUDS: PASS - every stacked tube sits on a parent stud"

    lines = [
        header + f"STUDS: FAIL - {len(faults)} unsupported tube(s)",
        "Off-stud / unsupported tubes:",
    ]
    for i, f in enumerate(faults, 1):
        lines.append(
            f"  [{i}] {f.child_id} ({get_part(f.child_part).name}) "
            f"on parent {f.parent_id}: {f.detail}"
        )
    return "\n".join(lines)
