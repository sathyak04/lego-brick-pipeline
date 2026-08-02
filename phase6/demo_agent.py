"""
Phase 6 demo — run the deterministic release agent on the locked sphere.

Builds the hollow sphere (Phase 1–5), then hill-climbs with Phase 6 actions
until READY or no progress. Soft-only: hard 1/0 gate must stay green.
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
from hollow_build import build_hollow_from_solid, fit_mesh  # noqa: E402
from scorecard import format_release_report  # noqa: E402
from voxelize import voxelize_solid  # noqa: E402
from demo_sphere import BASELINE_DIAMETER_STUDS  # noqa: E402
from loop import improve_release  # noqa: E402
from state import evaluate  # noqa: E402


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "output" / "phase6"
    out.mkdir(parents=True, exist_ok=True)

    diameter = BASELINE_DIAMETER_STUDS
    print(f"Building hollow sphere (diameter={diameter:.0f})...")
    sphere = make_uv_sphere(radius=1.0, stacks=16, slices=24)
    fit_mesh(sphere, diameter)
    solid = voxelize_solid(sphere, use_raycast=True)
    hollow = build_hollow_from_solid(solid, name="sphere")

    if not hollow.ok:
        print("BASELINE FAIL — agent refuses to polish a hard-fail model", file=sys.stderr)
        raise SystemExit(1)

    start = evaluate(
        hollow.bricks,
        interior_count=hollow.interior_count,
        solid_count=hollow.solid_count,
    )
    print()
    print("BEFORE agent:")
    print(format_release_report(start.release))
    print()
    print("Running Phase 6 hill-climber...")
    result = improve_release(start, max_rounds=25, verbose=True)

    print()
    print("AFTER agent:")
    print(format_release_report(result.final.release))
    print(
        f"  delta={result.delta:+.1f} accepted={result.accepted}/{len(result.log)} "
        f"parts {len(start.bricks)} -> {len(result.final.bricks)}"
    )

    export_bricks_to_io(
        result.final.bricks,
        out / "sphere_agent.io",
        name="Sphere after Phase 6 agent",
    )
    (out / "sphere_agent_report.txt").write_text(
        f"diameter={diameter}\n"
        f"delta={result.delta:+.1f} accepted={result.accepted}\n"
        f"log={[ (r.action, r.accepted, r.score_before, r.score_after, r.parts_added) for r in result.log ]}\n\n"
        "BEFORE\n"
        + format_release_report(result.initial.release)
        + "\n\nAFTER\n"
        + format_release_report(result.final.release),
        encoding="utf-8",
    )
    print(f"Wrote {out / 'sphere_agent.io'}")

    if not result.final.hard_ok:
        print("AGENT FAIL: hard gate broken", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"AGENT OK: hard gates held, score {result.initial.score:.1f} -> "
        f"{result.final.score:.1f}"
    )


if __name__ == "__main__":
    main()
