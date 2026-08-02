"""
Phase 6 suite demo — run the release agent on sphere + bunny + teapot.

Proves the loop is model-agnostic: same improve_release path for every shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase4"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_shapes import make_uv_sphere  # noqa: E402
from export_io import export_bricks_to_io  # noqa: E402
from hollow_build import (  # noqa: E402
    HollowResult,
    build_hollow_from_mesh,
    build_hollow_from_solid,
    fit_mesh,
)
from mesh import load_obj  # noqa: E402
from scorecard import format_release_report  # noqa: E402
from voxelize import voxelize_solid  # noqa: E402
from demo_sphere import BASELINE_DIAMETER_STUDS  # noqa: E402
from demo_suite import BUNNY_STUDS, TEAPOT_STUDS  # noqa: E402
from loop import ImproveResult, improve_release  # noqa: E402
from state import evaluate  # noqa: E402

MAX_ROUNDS = 30


def _run_agent(hollow: HollowResult, *, verbose: bool = True) -> ImproveResult:
    start = evaluate(
        hollow.bricks,
        interior_count=hollow.interior_count,
        solid_count=hollow.solid_count,
    )
    if verbose:
        print(f"\n=== {hollow.name} BEFORE ===")
        print(format_release_report(start.release))
        print(f"Running agent (max_rounds={MAX_ROUNDS})...")
    result = improve_release(start, max_rounds=MAX_ROUNDS, verbose=verbose)
    if verbose:
        print(f"\n=== {hollow.name} AFTER ===")
        print(format_release_report(result.final.release))
        print(
            f"  delta={result.delta:+.1f} accepted={result.accepted}/{len(result.log)} "
            f"parts {len(result.initial.bricks)} -> {len(result.final.bricks)}"
        )
    return result


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase6"
    out.mkdir(parents=True, exist_ok=True)
    meshes = root / "assets" / "meshes"

    results: list[tuple[str, ImproveResult]] = []

    print("=" * 60)
    print(f"AGENT 1/3: sphere (diameter={BASELINE_DIAMETER_STUDS:.0f})")
    print("=" * 60)
    sphere = make_uv_sphere(radius=1.0, stacks=16, slices=24)
    fit_mesh(sphere, BASELINE_DIAMETER_STUDS)
    solid = voxelize_solid(sphere, use_raycast=True)
    sphere_h = build_hollow_from_solid(solid, name="sphere")
    if not sphere_h.ok:
        print("sphere hard FAIL — abort", file=sys.stderr)
        raise SystemExit(1)
    results.append(("sphere", _run_agent(sphere_h)))
    export_bricks_to_io(
        results[-1][1].final.bricks, out / "sphere_agent.io", name="Sphere + agent"
    )

    print()
    print("=" * 60)
    print(f"AGENT 2/3: bunny (max~{BUNNY_STUDS:.0f})")
    print("=" * 60)
    bunny_h = build_hollow_from_mesh(
        load_obj(meshes / "bunny.obj"), name="bunny", max_studs=BUNNY_STUDS
    )
    if not bunny_h.ok:
        print("bunny hard FAIL — abort", file=sys.stderr)
        raise SystemExit(1)
    results.append(("bunny", _run_agent(bunny_h)))
    export_bricks_to_io(
        results[-1][1].final.bricks, out / "bunny_agent.io", name="Bunny + agent"
    )

    print()
    print("=" * 60)
    print(f"AGENT 3/3: teapot (max~{TEAPOT_STUDS:.0f})")
    print("=" * 60)
    teapot_h = build_hollow_from_mesh(
        load_obj(meshes / "teapot.obj"), name="teapot", max_studs=TEAPOT_STUDS
    )
    if not teapot_h.ok:
        print("teapot hard FAIL — abort", file=sys.stderr)
        raise SystemExit(1)
    results.append(("teapot", _run_agent(teapot_h)))
    export_bricks_to_io(
        results[-1][1].final.bricks, out / "teapot_agent.io", name="Teapot + agent"
    )

    lines = ["Phase 6 agent suite\n"]
    print()
    print("=" * 60)
    print("AGENT SUITE SUMMARY")
    print("=" * 60)
    failed_hard = []
    for name, r in results:
        hard = "PASS" if r.final.hard_ok else "FAIL"
        ready = "READY" if r.final.release.release_ready else "NOT READY"
        print(
            f"  {hard:4}  {name:8}  {r.initial.score:.1f} -> {r.final.score:.1f} "
            f"({r.delta:+.1f})  {ready}  accepted={r.accepted}"
        )
        lines.append(
            f"{name}: {r.initial.score:.1f}->{r.final.score:.1f} "
            f"delta={r.delta:+.1f} ready={r.final.release.release_ready} "
            f"hard_ok={r.final.hard_ok} accepted={r.accepted}\n"
        )
        if not r.final.hard_ok:
            failed_hard.append(name)

    (out / "agent_suite_report.txt").write_text("".join(lines), encoding="utf-8")
    print(f"\nOpen: {out / 'sphere_agent.io'}")
    print(f"      {out / 'bunny_agent.io'}")
    print(f"      {out / 'teapot_agent.io'}")

    if failed_hard:
        print(f"AGENT SUITE FAIL hard gates: {', '.join(failed_hard)}", file=sys.stderr)
        raise SystemExit(1)
    print("AGENT SUITE OK: hard gates held on all shapes")


if __name__ == "__main__":
    main()
