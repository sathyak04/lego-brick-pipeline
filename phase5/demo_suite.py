"""
Phase 5 Studio suite: three hollow shapes that stress the pipeline.

  1. sphere  — closed curved shell (locked baseline size)
  2. bunny   — organic overhangs / ears
  3. teapot  — thin handle + spout (hard clutch topology)

Exports full models only (no half-cuts):
  output/phase5/sphere_full.io
  output/phase5/bunny_full.io
  output/phase5/teapot_full.io
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
from mesh import load_obj  # noqa: E402
from voxelize import voxelize_solid  # noqa: E402
from connectivity import (  # noqa: E402
    format_connectivity_report,
    format_weak_edge_diagnosis,
)
from balance import format_report as format_balance  # noqa: E402
from overhang import format_overhang_report  # noqa: E402
from build_order import format_build_order_report  # noqa: E402
from scorecard import format_release_report  # noqa: E402
from hollow_build import (  # noqa: E402
    HollowResult,
    build_hollow_from_mesh,
    build_hollow_from_solid,
    fit_mesh,
)

# Sphere stays on the locked baseline size; mesh shapes use a workable stud budget.
SPHERE_DIAMETER = 20.0
BUNNY_STUDS = 24.0
TEAPOT_STUDS = 22.0


def _print_result(result: HollowResult) -> None:
    print(format_connectivity_report(result.report, result.bricks, strength=result.strength))
    print(format_weak_edge_diagnosis(result.weak_diag))
    print(format_balance(result.balance))
    print(format_overhang_report(result.overhang, result.bricks))
    print(format_build_order_report(result.build_order, result.bricks))
    print(format_release_report(result.release))
    verdict = "PASS" if result.ok else "FAIL"
    bal = "PASS" if result.balanced else "TIP"
    ov = "PASS" if result.supported else f"FAIL({len(result.overhang.unsupported_ids)})"
    bo = "PASS" if result.buildable else f"FAIL({len(result.build_order.blocked_ids)})"
    print(
        f"  [{verdict}] {result.name}: sections={result.report.section_count} "
        f"collisions={result.stats['collisions']} parts={len(result.bricks)} "
        f"hollow={result.hollow_pct:.0f}% "
        f"weak={result.strength.weak_edges}/{result.strength.edge_count} "
        f"mean={result.strength.mean_overlap:.2f} balance={bal} overhang={ov} "
        f"build={bo} release={result.release.score:.1f}/100"
    )


def _write_report(path: Path, result: HollowResult, header: str) -> None:
    path.write_text(
        header
        + f"\nstats={result.stats}\nmix={result.part_mix}\n"
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
        + format_build_order_report(result.build_order, result.bricks)
        + "\n"
        + format_release_report(result.release),
        encoding="utf-8",
    )


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase5"
    out.mkdir(parents=True, exist_ok=True)
    meshes = root / "assets" / "meshes"

    results: list[HollowResult] = []

    # --- sphere ---
    print("=" * 60)
    print(f"SHAPE 1/3: sphere (diameter={SPHERE_DIAMETER:.0f})")
    print("=" * 60)
    sphere = make_uv_sphere(radius=1.0, stacks=16, slices=24)
    fit_mesh(sphere, SPHERE_DIAMETER)
    print("Voxelizing sphere...")
    solid = voxelize_solid(sphere, use_raycast=True)
    sphere_r = build_hollow_from_solid(solid, name="sphere")
    _print_result(sphere_r)
    export_bricks_to_io(sphere_r.bricks, out / "sphere_full.io", name="Hollow sphere")
    _write_report(
        out / "sphere_report.txt",
        sphere_r,
        f"Hollow sphere diameter={SPHERE_DIAMETER} studs",
    )
    results.append(sphere_r)

    # --- bunny ---
    print()
    print("=" * 60)
    print(f"SHAPE 2/3: bunny (max~{BUNNY_STUDS:.0f} studs)")
    print("=" * 60)
    bunny = load_obj(meshes / "bunny.obj")
    bunny_r = build_hollow_from_mesh(bunny, name="bunny", max_studs=BUNNY_STUDS)
    _print_result(bunny_r)
    export_bricks_to_io(bunny_r.bricks, out / "bunny_full.io", name="Hollow bunny")
    _write_report(
        out / "bunny_report.txt",
        bunny_r,
        f"Hollow bunny max_studs={BUNNY_STUDS}",
    )
    results.append(bunny_r)

    # --- teapot (handle + spout stress) ---
    print()
    print("=" * 60)
    print(f"SHAPE 3/3: teapot (max~{TEAPOT_STUDS:.0f} studs) - handle/spout stress")
    print("=" * 60)
    teapot = load_obj(meshes / "teapot.obj")
    teapot_r = build_hollow_from_mesh(teapot, name="teapot", max_studs=TEAPOT_STUDS)
    _print_result(teapot_r)
    export_bricks_to_io(teapot_r.bricks, out / "teapot_full.io", name="Hollow teapot")
    _write_report(
        out / "teapot_report.txt",
        teapot_r,
        f"Hollow teapot max_studs={TEAPOT_STUDS}",
    )
    results.append(teapot_r)

    # Drop obsolete half-cut artifact if present
    half = out / "sphere_half_cut.io"
    if half.exists():
        half.unlink()

    (out / "OPEN_THESE.txt").write_text(
        "Open these three in Studio (full models, no half-cuts):\n\n"
        "1. sphere_full.io   — closed curved shell (baseline)\n"
        "2. bunny_full.io    — organic overhangs / ears\n"
        "3. teapot_full.io   — thin handle + spout (clutch stress)\n\n"
        "Hard PASS per model: 1 clutch section, 0 AABB collisions, hollow.\n"
        "Soft report: clutch strength, balance/tip, overhang, build order.\n",
        encoding="utf-8",
    )

    print()
    print("=" * 60)
    print("SUITE SUMMARY")
    print("=" * 60)
    failed = []
    tippy = []
    hanging = []
    unbuildable = []
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        bal = "PASS" if r.balanced else "TIP"
        ov = "PASS" if r.supported else f"FAIL({len(r.overhang.unsupported_ids)})"
        bo = "PASS" if r.buildable else f"FAIL({len(r.build_order.blocked_ids)})"
        print(
            f"  {mark:4}  {r.name:8}  sections={r.report.section_count}  "
            f"collisions={r.stats['collisions']}  parts={len(r.bricks)}  "
            f"weak={100.0 * r.strength.weak_ratio:.0f}%  "
            f"mean={r.strength.mean_overlap:.2f}  balance={bal}  "
            f"overhang={ov}  build={bo}  release={r.release.score:.1f}/100"
        )
        if not r.ok:
            failed.append(r.name)
        if not r.balanced:
            tippy.append(r.name)
        if not r.supported:
            hanging.append(r.name)
        if not r.buildable:
            unbuildable.append(r.name)
    print()
    print(f"Open: {out / 'OPEN_THESE.txt'}")
    print(f"  {out / 'sphere_full.io'}")
    print(f"  {out / 'bunny_full.io'}")
    print(f"  {out / 'teapot_full.io'}")

    if failed:
        print(f"SUITE FAIL: {', '.join(failed)}", file=sys.stderr)
        raise SystemExit(1)
    print("SUITE OK: sphere + bunny + teapot all 1 section / 0 collisions")
    if tippy:
        print(f"SOFT tip report: {', '.join(tippy)} (not a hard FAIL yet)")
    else:
        print("SOFT balance: all shapes PASS tip check")
    if hanging:
        print(f"SOFT overhang report: {', '.join(hanging)} (not a hard FAIL yet)")
    else:
        print("SOFT overhang: all pieces supported from ground")
    if unbuildable:
        print(
            f"SOFT build-order report: {', '.join(unbuildable)} "
            "(mid-air placements; not a hard FAIL yet)"
        )
    else:
        print("SOFT build-order: all shapes placeable bottom-up")


if __name__ == "__main__":
    main()
