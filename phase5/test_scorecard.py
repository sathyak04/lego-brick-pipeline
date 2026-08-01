"""Phase 5 — release scorecard unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from balance import BalanceReport  # noqa: E402
from build_order import BuildOrderReport  # noqa: E402
from connectivity import ClutchStrengthReport, ConnectivityReport  # noqa: E402
from export_io import Brick  # noqa: E402
from overhang import OverhangReport  # noqa: E402
from scorecard import score_release  # noqa: E402


def _bricks(n: int) -> list[Brick]:
    return [Brick("3005.dat", 15, 0.0, -24.0 * (i + 1), 0.0) for i in range(n)]


def _connectivity(n: int, sections: int) -> ConnectivityReport:
    per = max(1, n // sections)
    comps: list[list[int]] = []
    ids = list(range(n))
    for s in range(sections):
        comps.append(ids[s * per : (s + 1) * per] or [ids[-1]])
    component_of = [0] * n
    for ci, comp in enumerate(comps):
        for i in comp:
            component_of[i] = ci
    return ConnectivityReport(edges=[], components=comps, component_of=component_of)


def _strength(edges: int, weak: int, mean: float) -> ClutchStrengthReport:
    return ClutchStrengthReport(
        edge_count=edges, weak_edges=weak, mean_overlap=mean, overlaps=()
    )


def _balance(*, tip: bool) -> BalanceReport:
    return BalanceReport(
        com=(0.0, -100.0, 0.0),
        footprint_points=[(0.0, 0.0)],
        support_xz=(0.0, 0.0),
        inside=not tip,
        edge_margin_ldu=0.0 if tip else 40.0,
        min_margin_ldu=10.0,
        tip_hazard=tip,
        total_mass=1.0,
        ground_parts=4,
    )


def _clean_args(n: int = 10) -> dict:
    return dict(
        bricks=_bricks(n),
        connectivity=_connectivity(n, 1),
        strength=_strength(edges=20, weak=2, mean=2.6),
        balance=_balance(tip=False),
        overhang=OverhangReport(
            grounded_ids=[0], supported_ids=list(range(n)), unsupported_ids=[]
        ),
        build_order=BuildOrderReport(
            order=list(range(n)), blocked_ids=[], grounded_ids=[0]
        ),
        collisions=0,
        interior_count=50,
        solid_count=100,
    )


class TestScorecard(unittest.TestCase):
    def test_clean_model_is_release_ready(self) -> None:
        r = score_release(**_clean_args())
        self.assertTrue(r.release_ready)
        self.assertEqual(r.hard_failures, [])
        self.assertEqual(r.soft_issues, [])
        self.assertAlmostEqual(r.score, 100.0, places=6)

    def test_detached_sections_is_hard_failure(self) -> None:
        args = _clean_args()
        args["connectivity"] = _connectivity(10, 3)
        r = score_release(**args)
        self.assertFalse(r.release_ready)
        codes = [i.code for i in r.hard_failures]
        self.assertIn("detached_sections", codes)
        self.assertLess(r.score, 100.0)

    def test_collisions_is_hard_failure(self) -> None:
        args = _clean_args()
        args["collisions"] = 4
        r = score_release(**args)
        self.assertFalse(r.release_ready)
        self.assertIn("collisions", [i.code for i in r.hard_failures])

    def test_perfect_soft_cannot_mask_hard_gate(self) -> None:
        """A hard gate failure must cap the score below any soft-only failure."""
        hard = _clean_args()
        hard["collisions"] = 1
        soft = _clean_args()
        soft["balance"] = _balance(tip=True)
        self.assertLess(score_release(**hard).score, score_release(**soft).score)

    def test_soft_issues_listed_with_actions(self) -> None:
        args = _clean_args()
        args["balance"] = _balance(tip=True)
        args["build_order"] = BuildOrderReport(
            order=[0, 1], blocked_ids=[2, 3, 4], grounded_ids=[0]
        )
        args["overhang"] = OverhangReport(
            grounded_ids=[0], supported_ids=[0, 1], unsupported_ids=[5]
        )
        r = score_release(**args)
        self.assertFalse(r.release_ready)
        self.assertEqual(r.hard_failures, [])
        codes = [i.code for i in r.soft_issues]
        self.assertIn("tip_hazard", codes)
        self.assertIn("mid_air_pieces", codes)
        self.assertIn("unsupported_pieces", codes)
        for issue in r.soft_issues:
            self.assertTrue(issue.suggested_action)

    def test_issues_are_prioritized_hard_first(self) -> None:
        args = _clean_args()
        args["collisions"] = 2
        args["balance"] = _balance(tip=True)
        r = score_release(**args)
        self.assertEqual(r.issues[0].severity, "hard")

    def test_solid_fill_flags_not_hollow(self) -> None:
        args = _clean_args()
        args["interior_count"] = 0
        r = score_release(**args)
        self.assertIn("not_hollow", [i.code for i in r.hard_failures])

    def test_blind_spots_reported(self) -> None:
        r = score_release(**_clean_args())
        self.assertIn("part_count_bloat", r.unmeasured)
        self.assertIn("shear_planes", r.unmeasured)


if __name__ == "__main__":
    unittest.main(verbosity=2)
