"""
Phase 6 — model state for the release-readiness loop.

Re-runs Phase 5 validators on a brick list and returns a single snapshot the
hill-climber can compare before/after a fix action.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5"))

from balance import check_balance  # noqa: E402
from bloat import check_bloat  # noqa: E402
from brick_collision import count_collisions  # noqa: E402
from build_order import check_build_order  # noqa: E402
from connectivity import check_connectivity, clutch_strength  # noqa: E402
from export_io import Brick  # noqa: E402
from hollow_build import BALANCE_MIN_MARGIN_STUDS  # noqa: E402
from interlock import check_interlock  # noqa: E402
from overhang import check_overhangs  # noqa: E402
from scorecard import ReleaseReport, score_release  # noqa: E402


@dataclass
class ModelState:
    bricks: list[Brick]
    release: ReleaseReport
    collisions: int
    sections: int
    interior_count: int
    solid_count: int

    @property
    def score(self) -> float:
        return self.release.score

    @property
    def hard_ok(self) -> bool:
        return (
            self.sections <= 1
            and self.collisions == 0
            and (self.solid_count == 0 or self.interior_count > 0)
        )


def evaluate(
    bricks: list[Brick],
    *,
    interior_count: int = 0,
    solid_count: int = 0,
    min_margin_studs: float = BALANCE_MIN_MARGIN_STUDS,
) -> ModelState:
    connectivity = check_connectivity(bricks)
    strength = clutch_strength(bricks, connectivity)
    balance = check_balance(bricks, min_margin_studs=min_margin_studs)
    overhang = check_overhangs(bricks)
    build_order = check_build_order(bricks)
    bloat = check_bloat(bricks)
    interlock = check_interlock(bricks)
    collisions = count_collisions(bricks)
    release = score_release(
        bricks=bricks,
        connectivity=connectivity,
        strength=strength,
        balance=balance,
        overhang=overhang,
        build_order=build_order,
        bloat=bloat,
        interlock=interlock,
        collisions=collisions,
        interior_count=interior_count,
        solid_count=solid_count,
    )
    return ModelState(
        bricks=list(bricks),
        release=release,
        collisions=collisions,
        sections=connectivity.section_count,
        interior_count=interior_count,
        solid_count=solid_count,
    )
