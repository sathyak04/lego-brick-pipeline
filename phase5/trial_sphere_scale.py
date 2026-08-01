"""One-off scale trial: hollow sphere at a given diameter (default 18)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase4"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_shapes import make_uv_sphere  # noqa: E402
from export_io import export_bricks_to_io  # noqa: E402
from voxelize import voxelize_solid  # noqa: E402
from connectivity import (  # noqa: E402
    format_connectivity_report,
    format_weak_edge_diagnosis,
)
from hollow_build import build_hollow_from_solid, fit_mesh  # noqa: E402


def main() -> None:
    diameter = float(sys.argv[1]) if len(sys.argv) > 1 else 18.0
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase5"
    out.mkdir(parents=True, exist_ok=True)

    print(f"TRY hollow sphere diameter={diameter:.0f}")
    sphere = make_uv_sphere(radius=1.0, stacks=16, slices=24)
    fit_mesh(sphere, diameter)
    print("Voxelizing...")
    solid = voxelize_solid(sphere, use_raycast=True)
    result = build_hollow_from_solid(solid, name=f"sphere_{diameter:.0f}")
    print(format_connectivity_report(result.report, result.bricks, strength=result.strength))
    print(format_weak_edge_diagnosis(result.weak_diag))
    print(
        f"VERDICT ok={result.ok} sections={result.report.section_count} "
        f"collisions={result.stats['collisions']} parts={len(result.bricks)} "
        f"hollow={result.hollow_pct:.0f}%"
    )
    path = out / f"sphere_d{diameter:.0f}_trial.io"
    export_bricks_to_io(
        result.bricks, path, name=f"Hollow sphere d{diameter:.0f} trial"
    )
    print(f"Wrote {path}")
    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
