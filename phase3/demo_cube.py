"""
Phase 3, Step 1 demo — unit cube mesh → 1x1 brick voxels → .io

Creates a small box (4 x 3 x 2 studs), voxelizes solid fill, exports Studio file.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import BRICK_H, STUD  # noqa: E402
from mesh import make_box, write_obj  # noqa: E402
from voxelize import export_voxels_io, voxelize_solid  # noqa: E402


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "output" / "phase3"
    out.mkdir(parents=True, exist_ok=True)

    # 4 studs X, 3 bricks Y, 2 studs Z — sitting on y=0
    sx, sy, sz = 4, 3, 2
    mesh = make_box(0.0, 0.0, 0.0, sx * STUD, sy * BRICK_H, sz * STUD)
    obj_path = write_obj(mesh, out / "cube.obj")

    voxels = voxelize_solid(mesh, use_raycast=False)
    io_path = export_voxels_io(
        voxels,
        out / "phase3_step1_cube.io",
        name="Phase3 Step1 Cube 4x3x2",
        color=4,  # red
    )

    print(f"Mesh:   {obj_path}")
    print(f"Size:   {sx} x {sy} x {sz} studs/bricks")
    print(f"Voxels: {len(voxels)} (expected {sx * sy * sz})")
    print(f"Wrote:  {io_path}")
    print("Open the .io in Studio — should be a solid red rectangular block of 1x1s.")


if __name__ == "__main__":
    main()
