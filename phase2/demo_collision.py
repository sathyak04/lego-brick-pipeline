"""
Phase 2, Step 2+3 demo — LEGAL vs ILLEGAL with collisions AND stud checks.

Studio shows bricks only. Verdict is in:
  output/phase2_step2_report.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from export_io import export_bricks_to_io  # noqa: E402
from collision import find_collisions, report_collisions  # noqa: E402
from connections import find_stud_faults, report_stud_faults  # noqa: E402
from scene import (  # noqa: E402
    BrickNode,
    SceneGraph,
    root_on_ground,
    stack_on_studs,
)
from transform import Transform  # noqa: E402


def build_legal() -> SceneGraph:
    """
    Every tube on a real stud (should PASS collisions + studs):

      yellow 2x4 plate
        └─ red 2x4
             ├─ cyan slope L / R  (cover the 2x4)
      white 2x4 plate beside it
        ├─ green 2x2 (left half)
        └─ blue 2x2 (right half)   # was a 1x2 centered between stud rows — illegal
             note: tower 1x1 sits on a CORNER stud of the green 2x2 (±0.5, ±0.5)
               └─ black 1x1 plate
    """
    g = SceneGraph()

    base_l = BrickNode(id="base_left", part_id="3020.dat", color=14)
    base_r = BrickNode(id="base_right", part_id="3020.dat", color=15)
    wall = BrickNode(id="wall_red", part_id="3001.dat", color=4)
    mid_a = BrickNode(id="mid_green", part_id="3003.dat", color=2)
    mid_b = BrickNode(id="mid_blue", part_id="3003.dat", color=1)  # 2x2, not 1x2
    slope_l = BrickNode(id="slope_l", part_id="3039.dat", color=3)
    slope_r = BrickNode(id="slope_r", part_id="3039.dat", color=3)
    tower = BrickNode(id="tower_1x1", part_id="3005.dat", color=25)
    cap = BrickNode(id="cap_plate", part_id="3024.dat", color=0)

    g.add_root(base_l, root_on_ground("3020.dat", sx=0.0))
    g.add_root(base_r, root_on_ground("3020.dat", sx=4.0))

    base_l.add_child(wall, stack_on_studs("3001.dat"))
    base_r.add_child(mid_a, stack_on_studs("3003.dat", sx=-1.0))
    base_r.add_child(mid_b, stack_on_studs("3003.dat", sx=1.0))

    wall.add_child(slope_l, stack_on_studs("3039.dat", sx=-1.0))
    wall.add_child(slope_r, stack_on_studs("3039.dat", sx=1.0))

    # 1x1 must sit ON a stud of the 2x2, not at the 2x2 center (between studs).
    mid_a.add_child(tower, stack_on_studs("3005.dat", sx=-0.5, sz=-0.5))
    tower.add_child(cap, stack_on_studs("3024.dat"))

    return g


def build_illegal() -> SceneGraph:
    """
    Deliberate crimes (should FAIL):

      COLLISION crimes:
        1. ghost_dup — second 2x4 in wall_red's slot
        2. spear     — 1x2 jammed into wall at same height

      OFF-STUD crimes (no collision, still illegal):
        3. float_1x2 — 1x2 centered on white plate (straddles stud rows in Z)
        4. between   — 1x1 at center of green 2x2 (between four studs)
    """
    g = SceneGraph()

    base_l = BrickNode(id="base_left", part_id="3020.dat", color=14)
    base_r = BrickNode(id="base_right", part_id="3020.dat", color=15)
    wall = BrickNode(id="wall_red", part_id="3001.dat", color=4)
    mid_a = BrickNode(id="mid_green", part_id="3003.dat", color=2)

    ghost = BrickNode(id="ghost_dup", part_id="3001.dat", color=7)
    spear = BrickNode(id="spear", part_id="3004.dat", color=25)
    float_1x2 = BrickNode(id="float_1x2", part_id="3004.dat", color=1)
    between = BrickNode(id="between_studs", part_id="3005.dat", color=25)

    g.add_root(base_l, root_on_ground("3020.dat", sx=0.0))
    g.add_root(base_r, root_on_ground("3020.dat", sx=4.0))

    base_l.add_child(wall, stack_on_studs("3001.dat"))
    base_r.add_child(mid_a, stack_on_studs("3003.dat", sx=-1.0))

    # Collisions
    base_l.add_child(ghost, stack_on_studs("3001.dat"))
    base_l.add_child(spear, stack_on_studs("3004.dat", sx=1.0))

    # Off-stud (these were the silent bugs in the old "legal" file)
    base_r.add_child(float_1x2, stack_on_studs("3004.dat", sx=1.0, sz=0.0))
    mid_a.add_child(between, stack_on_studs("3005.dat", sx=0.0, sz=0.0))

    return g


def full_report(scene: SceneGraph, title: str) -> str:
    col = report_collisions(scene, title=title)
    stud = report_stud_faults(scene)
    n_col = len(find_collisions(scene))
    n_stud = len(find_stud_faults(scene))
    overall = "PASS" if n_col == 0 and n_stud == 0 else "FAIL"
    return (
        col
        + "\n"
        + stud
        + "\n"
        + f"OVERALL VERDICT: {overall} "
        + f"(collisions={n_col}, stud_faults={n_stud})"
    )


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    legal = build_legal()
    illegal = build_illegal()

    legal_text = full_report(legal, "LEGAL build")
    illegal_text = full_report(illegal, "ILLEGAL build")

    print(legal_text)
    print()
    print(illegal_text)

    assert find_collisions(legal) == [], "legal must have no collisions"
    assert find_stud_faults(legal) == [], "legal must have all tubes on studs"
    assert find_collisions(illegal) or find_stud_faults(illegal), "illegal must fail"

    p1 = export_bricks_to_io(
        legal.to_bricks(),
        out_dir / "phase2_step2_legal.io",
        name="LEGAL - on studs, no collisions",
    )
    p2 = export_bricks_to_io(
        illegal.to_bricks(),
        out_dir / "phase2_step2_illegal.io",
        name="ILLEGAL - collisions and off-stud",
    )

    report_path = out_dir / "phase2_step2_report.txt"
    report_path.write_text(
        legal_text
        + "\n\n"
        + illegal_text
        + "\n\n"
        + "Studio files:\n"
        + f"  LEGAL:   {p1}\n"
        + f"  ILLEGAL: {p2}\n"
        + "\nStudio does not show PASS/FAIL — read this report.\n"
        + "ILLEGAL visual cues: grey twin, orange spear, blue 1x2 between stud rows, "
        + "orange 1x1 sitting in the middle of the green 2x2 (between studs).\n",
        encoding="utf-8",
    )

    print()
    print(f"Wrote: {p1}")
    print(f"Wrote: {p2}")
    print(f"Wrote: {report_path}")


if __name__ == "__main__":
    main()
