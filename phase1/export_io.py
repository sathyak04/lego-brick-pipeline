"""
Phase 1, Step 3 — Stacked mini-build → .io export.

Blueprint anchor: Phase 1 (LDraw & ".io" Export Pipeline).
Validates vertical stacking math + simple yaw for opposite-facing slopes.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from catalog import CATALOG, get_part, py_above, py_on_ground, studs_to_ldu

# LDraw line-type-1 rotation: a b c d e f g h i  →  [[a d g],[b e h],[c f i]]
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
# 180° about Y (vertical): X and Z flip — faces the slope the other way.
YAW_180 = (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -1.0)


@dataclass(frozen=True)
class Brick:
    """One placed part in LDraw LDU space."""

    part_id: str
    color: int
    x: float
    y: float
    z: float
    # Row-major LDraw a..i rotation terms
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0
    e: float = 1.0
    f: float = 0.0
    g: float = 0.0
    h: float = 0.0
    i: float = 1.0


def place(
    part_id: str,
    color: int,
    sx: float,
    py: float,
    sz: float,
    yaw_180: bool = False,
) -> Brick:
    """
    Place a catalog part on the stud / plate-height grid.

    Catalog ox/oz are local footprint corrections; if yaw_180, they flip
    with the part so the slope still sits correctly on the grid.
    """
    spec = get_part(part_id)
    ox, oz = spec.ox, spec.oz
    rot = YAW_180 if yaw_180 else IDENTITY
    if yaw_180:
        # 180° about Y: (x, z) → (-x, -z)
        ox, oz = -ox, -oz

    x, y, z = studs_to_ldu(sx + ox, py, sz + oz)
    return Brick(
        part_id=part_id,
        color=color,
        x=x,
        y=y,
        z=z,
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


def bricks_to_ldr(bricks: list[Brick], name: str = "Untitled") -> str:
    """Format bricks into a valid LDraw model string (line type 1)."""
    lines = [
        "0 FILE model.ldr",
        f"0 {name}",
        "0 Name: model.ldr",
        "0 Author: LEGO Release Readiness Engine",
        "0 !LDRAW_ORG Unofficial_Model",
    ]
    for b in bricks:
        lines.append(
            f"1 {b.color} {b.x:.1f} {b.y:.1f} {b.z:.1f} "
            f"{b.a:.0f} {b.b:.0f} {b.c:.0f} "
            f"{b.d:.0f} {b.e:.0f} {b.f:.0f} "
            f"{b.g:.0f} {b.h:.0f} {b.i:.0f} {b.part_id}"
        )
    lines.append("")
    return "\n".join(lines)


def write_io(ldr_text: str, output_path: Path) -> Path:
    """Zip model.ldr into a BrickLink Studio .io archive."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("model.ldr", ldr_text)
    return output_path


def export_bricks_to_io(
    bricks: list[Brick],
    output_path: Path,
    name: str = "Untitled",
) -> Path:
    """Bricks → LDR string → .io on disk."""
    return write_io(bricks_to_ldr(bricks, name=name), output_path)


def build_catalog_demo() -> list[Brick]:
    """Step 2 visual: every catalog part in a row (flat, no stacking)."""
    colors = [4, 1, 2, 14, 15, 0, 7, 6, 25, 3]
    bricks: list[Brick] = []
    cursor_sx = 0.0

    for i, (part_id, spec) in enumerate(CATALOG.items()):
        sx = cursor_sx + spec.width / 2.0
        sz = spec.depth / 2.0
        bricks.append(place(part_id, colors[i], sx=sx, py=0.0, sz=sz))
        cursor_sx += spec.width + 1

    return bricks


def build_stacked_mini() -> list[Brick]:
    """
    Step 3 visual: symmetric slope overhangs from the side.

      - yellow plate + red 2x4
      - 2 blue slopes facing default, hanging 1 stud off the -Z edge
      - 2 blue slopes facing opposite (180° yaw), hanging 1 stud off +Z

    Side view should look symmetric: slope bottoms hanging both ways.
    """
    plate = "3020.dat"
    wall = "3001.dat"
    slope = "3039.dat"

    py0 = py_on_ground(plate)
    py1 = py_above(py0, plate, wall)
    py2 = py_above(py1, wall, slope)

    return [
        place(plate, 14, sx=0.0, py=py0, sz=0.0),
        place(wall, 4, sx=0.0, py=py1, sz=0.0),
        # Front pair — default facing, hang off -Z
        place(slope, 1, sx=-1.0, py=py2, sz=-1.0),
        place(slope, 1, sx=1.0, py=py2, sz=-1.0),
        # Back pair — opposite facing, hang off +Z
        place(slope, 1, sx=-1.0, py=py2, sz=1.0, yaw_180=True),
        place(slope, 1, sx=1.0, py=py2, sz=1.0, yaw_180=True),
    ]


def main() -> None:
    bricks = build_stacked_mini()
    name = "Phase1 Step3 Symmetric Overhang"
    out = (
        Path(__file__).resolve().parent.parent
        / "output"
        / "phase1_step3_stacked.io"
    )
    path = export_bricks_to_io(bricks, out, name=name)

    print(f"Wrote: {path}")
    print(f"Parts: {len(bricks)}")
    print("--- parts ---")
    for b in bricks:
        spec = get_part(b.part_id)
        facing = "yaw180" if b.a < 0 else "default"
        print(
            f"  {spec.name:16} color={b.color}  "
            f"pos=({b.x:.0f},{b.y:.0f},{b.z:.0f})  {facing}"
        )
    print("--- model.ldr preview ---")
    print(bricks_to_ldr(bricks, name=name))


if __name__ == "__main__":
    main()
