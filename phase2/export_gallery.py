"""
Export 5 LEGAL + 5 ILLEGAL builds for visual inspection in Studio.

Writes:
  output/gallery/legal_01..05.io
  output/gallery/illegal_01..05.io
  output/gallery/INDEX.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_io import export_bricks_to_io  # noqa: E402
from collision import find_collisions  # noqa: E402
from connections import find_stud_faults  # noqa: E402
from scene import BrickNode, SceneGraph, root_on_ground, stack_on_studs  # noqa: E402
from transform import Transform  # noqa: E402


def verdict(scene: SceneGraph) -> str:
    cols = find_collisions(scene)
    studs = find_stud_faults(scene)
    if not cols and not studs:
        return "PASS"
    bits = []
    if cols:
        bits.append(f"{len(cols)} collision(s): " + ", ".join(f"{c.a_id}|{c.b_id}" for c in cols))
    if studs:
        bits.append(f"{len(studs)} off-stud: " + ", ".join(f"{s.child_id}" for s in studs))
    return "FAIL - " + "; ".join(bits)


# ---------- LEGAL ----------
def legal_01_plate_brick() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    p = BrickNode("plate", "3020.dat", 14)
    b = BrickNode("brick", "3001.dat", 4)
    g.add_root(p, root_on_ground("3020.dat"))
    p.add_child(b, stack_on_studs("3001.dat"))
    return g, "Yellow plate + red 2x4 on top (basic stack)"


def legal_02_two_2x2_on_plate() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    p = BrickNode("plate", "3020.dat", 15)
    a = BrickNode("left", "3003.dat", 2)
    b = BrickNode("right", "3003.dat", 1)
    g.add_root(p, root_on_ground("3020.dat"))
    p.add_child(a, stack_on_studs("3003.dat", sx=-1.0))
    p.add_child(b, stack_on_studs("3003.dat", sx=1.0))
    return g, "White plate covered by green + blue 2x2"


def legal_03_1x1_on_corner() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    p = BrickNode("base", "3003.dat", 4)
    t = BrickNode("tower", "3005.dat", 25)
    c = BrickNode("cap", "3024.dat", 0)
    g.add_root(p, root_on_ground("3003.dat"))
    p.add_child(t, stack_on_studs("3005.dat", sx=-0.5, sz=-0.5))
    t.add_child(c, stack_on_studs("3024.dat"))
    return g, "Red 2x2 + orange 1x1 on a corner stud + black plate cap"


def legal_04_slopes_on_2x4() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    w = BrickNode("wall", "3001.dat", 4)
    s1 = BrickNode("slope_l", "3039.dat", 1)
    s2 = BrickNode("slope_r", "3039.dat", 1)
    g.add_root(w, root_on_ground("3001.dat"))
    w.add_child(s1, stack_on_studs("3039.dat", sx=-1.0))
    w.add_child(s2, stack_on_studs("3039.dat", sx=1.0))
    return g, "Red 2x4 with two blue slopes flush on top"


def legal_05_mini_house() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    floor = BrickNode("floor", "3020.dat", 14)
    wall = BrickNode("wall", "3001.dat", 4)
    s1 = BrickNode("slope_l", "3039.dat", 3)
    s2 = BrickNode("slope_r", "3039.dat", 3)
    side = BrickNode("side_plate", "3020.dat", 15)
    col = BrickNode("col", "3003.dat", 2)
    tip = BrickNode("tip", "3005.dat", 25)
    g.add_root(floor, root_on_ground("3020.dat", sx=0.0))
    g.add_root(side, root_on_ground("3020.dat", sx=4.0))
    floor.add_child(wall, stack_on_studs("3001.dat"))
    wall.add_child(s1, stack_on_studs("3039.dat", sx=-1.0))
    wall.add_child(s2, stack_on_studs("3039.dat", sx=1.0))
    side.add_child(col, stack_on_studs("3003.dat", sx=-1.0))
    col.add_child(tip, stack_on_studs("3005.dat", sx=-0.5, sz=0.5))
    return g, "Mini scene: roofed wall + side tower on corner stud"


# ---------- ILLEGAL ----------
def illegal_01_1x1_between_studs() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    p = BrickNode("base", "3003.dat", 2)
    bad = BrickNode("between", "3005.dat", 25)
    g.add_root(p, root_on_ground("3003.dat"))
    p.add_child(bad, stack_on_studs("3005.dat", sx=0.0, sz=0.0))
    return g, "OFF-STUD: orange 1x1 centered on green 2x2 (between 4 studs)"


def illegal_02_1x2_straddle_rows() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    p = BrickNode("plate", "3020.dat", 15)
    bad = BrickNode("straddle", "3004.dat", 1)
    g.add_root(p, root_on_ground("3020.dat"))
    p.add_child(bad, stack_on_studs("3004.dat", sx=0.0, sz=0.0))
    return g, "OFF-STUD: blue 1x2 centered on plate (between stud rows)"


def illegal_03_half_stud_slide() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    p = BrickNode("plate", "3020.dat", 14)
    bad = BrickNode("slid", "3001.dat", 4)
    g.add_root(p, root_on_ground("3020.dat"))
    p.add_child(bad, stack_on_studs("3001.dat", sx=0.5))
    return g, "OFF-STUD: red 2x4 shifted half a stud on yellow plate"


def illegal_04_duplicate_slot() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    p = BrickNode("plate", "3020.dat", 14)
    a = BrickNode("red", "3001.dat", 4)
    b = BrickNode("ghost", "3001.dat", 7)
    g.add_root(p, root_on_ground("3020.dat"))
    p.add_child(a, stack_on_studs("3001.dat"))
    p.add_child(b, stack_on_studs("3001.dat"))
    return g, "COLLISION: grey 2x4 fused through red 2x4 (same slot)"


def illegal_05_jab_and_sink() -> tuple[SceneGraph, str]:
    g = SceneGraph()
    p = BrickNode("plate", "3020.dat", 15)
    wall = BrickNode("wall", "3001.dat", 4)
    jab = BrickNode("jab", "3004.dat", 25)
    sink = BrickNode("sink", "3003.dat", 0)
    g.add_root(p, root_on_ground("3020.dat"))
    p.add_child(wall, stack_on_studs("3001.dat"))
    p.add_child(jab, stack_on_studs("3004.dat", sx=1.0))
    p.add_child(sink, Transform.translation(-20.0, -12.0, 0.0))
    return g, "COLLISION: orange jab into red + black 2x2 sunk halfway"


LEGAL = [
    ("legal_01", legal_01_plate_brick),
    ("legal_02", legal_02_two_2x2_on_plate),
    ("legal_03", legal_03_1x1_on_corner),
    ("legal_04", legal_04_slopes_on_2x4),
    ("legal_05", legal_05_mini_house),
]

ILLEGAL = [
    ("illegal_01", illegal_01_1x1_between_studs),
    ("illegal_02", illegal_02_1x2_straddle_rows),
    ("illegal_03", illegal_03_half_stud_slide),
    ("illegal_04", illegal_04_duplicate_slot),
    ("illegal_05", illegal_05_jab_and_sink),
]


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "output" / "gallery"
    out.mkdir(parents=True, exist_ok=True)

    lines = [
        "GALLERY — open each .io in BrickLink Studio",
        "Engine verdict is also listed here (Studio will not show PASS/FAIL).",
        "",
        "===== LEGAL (should all be PASS) =====",
        "",
    ]

    print("Exporting LEGAL builds...")
    for key, fn in LEGAL:
        g, desc = fn()
        v = verdict(g)
        path = export_bricks_to_io(g.to_bricks(), out / f"{key}.io", name=f"LEGAL {key}")
        lines.append(f"{key}.io")
        lines.append(f"  what:    {desc}")
        lines.append(f"  verdict: {v}")
        lines.append(f"  file:    {path}")
        lines.append("")
        print(f"  {key}: {v}")

    lines.append("===== ILLEGAL (should all be FAIL) =====")
    lines.append("")

    print("Exporting ILLEGAL builds...")
    for key, fn in ILLEGAL:
        g, desc = fn()
        v = verdict(g)
        path = export_bricks_to_io(g.to_bricks(), out / f"{key}.io", name=f"ILLEGAL {key}")
        lines.append(f"{key}.io")
        lines.append(f"  what:    {desc}")
        lines.append(f"  verdict: {v}")
        lines.append(f"  file:    {path}")
        lines.append("")
        print(f"  {key}: {v}")

    index = out / "INDEX.txt"
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print(f"Index: {index}")
    print("Open the 10 .io files in Studio; read INDEX.txt for what each one is.")


if __name__ == "__main__":
    main()
