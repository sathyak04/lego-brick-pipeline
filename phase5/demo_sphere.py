"""
Hollow sphere connectivity + balance test (locked diameter baseline).

Exports:
  - sphere_full.io   complete hollow connected sphere
"""

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
from balance import format_report as format_balance  # noqa: E402
from overhang import format_overhang_report  # noqa: E402
from build_order import format_build_order_report  # noqa: E402
from hollow_build import (  # noqa: E402
    PASS_COLLISIONS,
    PASS_SECTIONS,
    build_hollow_from_solid,
    fit_mesh,
)

# Locked green baseline — do not raise until this diameter stays PASS.
BASELINE_DIAMETER_STUDS = 20.0
SOFT_WEAK_RATIO = 0.50
SOFT_MEAN_OVERLAP = 2.0


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase5"
    out.mkdir(parents=True, exist_ok=True)

    diameter = BASELINE_DIAMETER_STUDS
    print(f"Building UV sphere (diameter={diameter:.0f} studs, locked baseline)...")
    sphere = make_uv_sphere(radius=1.0, stacks=16, slices=24)
    fit_mesh(sphere, diameter)

    print("Voxelizing...")
    solid = voxelize_solid(sphere, use_raycast=True)
    result = build_hollow_from_solid(solid, name="sphere")

    print(format_connectivity_report(result.report, result.bricks, strength=result.strength))
    print(format_weak_edge_diagnosis(result.weak_diag))
    print(format_balance(result.balance))
    print(format_overhang_report(result.overhang, result.bricks))
    print(format_build_order_report(result.build_order, result.bricks))

    export_bricks_to_io(
        result.bricks, out / "sphere_full.io", name="Hollow sphere (full)"
    )

    (out / "sphere_report.txt").write_text(
        f"Hollow sphere diameter={diameter} studs\n"
        f"stats={result.stats}\nmix={result.part_mix}\n"
        + format_connectivity_report(
            result.report, result.bricks, strength=result.strength
        )
        + "\n"
        + format_weak_edge_diagnosis(result.weak_diag)
        + "\n"
        + format_balance(result.balance)
        + "\n"
        + format_overhang_report(result.overhang, result.bricks)
        + "\n"
        + format_build_order_report(result.build_order, result.bricks),
        encoding="utf-8",
    )

    print()
    print(f"Full:  {out / 'sphere_full.io'}")
    print(
        f"Exposed top studs: {result.stats['uncovered_studs']} | "
        f"collisions: {result.stats['collisions']} | "
        f"detached: {result.stats['sections_final']} | "
        f"balance: {'PASS' if result.balanced else 'TIP'} | "
        f"overhang: {'PASS' if result.supported else 'FAIL'} | "
        f"build: {'PASS' if result.buildable else 'FAIL'}"
    )

    if not result.ok:
        print(
            f"BASELINE FAIL: need {PASS_SECTIONS} section / {PASS_COLLISIONS} collisions; "
            f"got {result.report.section_count} / {result.stats['collisions']}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(
        f"BASELINE OK: diameter={diameter:.0f} "
        f"sections={result.report.section_count} "
        f"collisions={result.stats['collisions']} "
        f"weak_edges={result.strength.weak_edges}/{result.strength.edge_count} "
        f"mean_overlap={result.strength.mean_overlap:.2f} "
        f"balance={'PASS' if result.balanced else 'TIP'}"
    )
    soft_ok = (
        result.strength.weak_ratio <= SOFT_WEAK_RATIO
        and result.strength.mean_overlap >= SOFT_MEAN_OVERLAP
    )
    print(
        f"SOFT clutch: weak_ratio={100.0 * result.strength.weak_ratio:.0f}% "
        f"(goal <={100.0 * SOFT_WEAK_RATIO:.0f}%) "
        f"mean={result.strength.mean_overlap:.2f} "
        f"(goal >={SOFT_MEAN_OVERLAP:.1f}) "
        f"{'OK' if soft_ok else 'SHORT'}"
    )


if __name__ == "__main__":
    main()
