"""
Phase 5 — Release scorecard (the Agent's audit surface).

Blueprint anchor: Phase 5 "The Release Validator (The Agent's Toolkit)".
This module does not validate anything new; it folds the existing
validators into one prioritized audit the Phase 6 loop can read.

Scoring model:
  Each validator becomes a component score in [0, 1], then a weighted sum
  scaled to 0-100. Weights sum to 1.0.

    connectivity  0.25   hard gate — 1 clutch section
    collisions    0.20   hard gate — 0 AABB intersections
    balance       0.15   soft — CoM margin vs footprint
    overhang      0.15   soft — pieces reachable from ground
    build order   0.15   soft — pieces placeable bottom-up
    clutch        0.10   soft — stud overlap strength

  Hollowness is a hard gate but carries no weight (it is a construction
  property, not a quality dial).

Hard-gate dominance:
  A model failing any hard gate is capped at HARD_FAIL_CAP (40), which sits
  below the 45-point floor of any model that passes both weighted hard
  gates. So good soft numbers can never buy a release-ready verdict.

Each issue carries an `impact` (points lost) and a `suggested_action` name,
so the Phase 6 loop can always pick the highest-value fix to attempt next.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from balance import BalanceReport  # noqa: E402
from build_order import BuildOrderReport  # noqa: E402
from connectivity import ClutchStrengthReport, ConnectivityReport  # noqa: E402
from export_io import Brick  # noqa: E402
from overhang import OverhangReport  # noqa: E402

W_CONNECTIVITY = 0.25
W_COLLISIONS = 0.20
W_BALANCE = 0.15
W_OVERHANG = 0.15
W_BUILD_ORDER = 0.15
W_CLUTCH = 0.10

HARD_FAIL_CAP = 40.0

# Soft clutch goals (match demo_sphere reporting).
SOFT_WEAK_RATIO = 0.50
SOFT_MEAN_OVERLAP = 2.0

# Release Standards with no validator yet — the agent must know its blind spots.
UNMEASURED = ("part_count_bloat", "shear_planes", "micro_stress")


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str  # "hard" | "soft"
    detail: str
    count: int
    impact: float  # points lost out of 100
    suggested_action: str


@dataclass(frozen=True)
class ReleaseReport:
    score: float
    hard_failures: list[Issue]
    soft_issues: list[Issue]
    components: dict[str, float]
    metrics: dict[str, float]
    unmeasured: tuple[str, ...] = field(default=UNMEASURED)

    @property
    def release_ready(self) -> bool:
        return not self.hard_failures and not self.soft_issues

    @property
    def issues(self) -> list[Issue]:
        """Hard failures first, then soft — each group by descending impact."""
        return list(self.hard_failures) + list(self.soft_issues)

    @property
    def next_action(self) -> str | None:
        return self.issues[0].suggested_action if self.issues else None

    @property
    def verdict(self) -> str:
        if self.release_ready:
            return f"READY FOR RELEASE - score {self.score:.1f}/100"
        if self.hard_failures:
            return (
                f"BLOCKED - {len(self.hard_failures)} hard gate failure(s), "
                f"score {self.score:.1f}/100"
            )
        return (
            f"NOT READY - {len(self.soft_issues)} soft issue(s), "
            f"score {self.score:.1f}/100"
        )


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def score_release(
    *,
    bricks: list[Brick],
    connectivity: ConnectivityReport,
    strength: ClutchStrengthReport,
    balance: BalanceReport,
    overhang: OverhangReport,
    build_order: BuildOrderReport,
    collisions: int,
    interior_count: int = 0,
    solid_count: int = 0,
) -> ReleaseReport:
    n = max(len(bricks), 1)

    sections = connectivity.section_count
    conn_score = 1.0 if sections <= 1 else 1.0 / sections
    coll_score = 1.0 if collisions <= 0 else _clamp01(1.0 - collisions / n)

    if balance.min_margin_ldu > 0:
        bal_score = _clamp01(balance.edge_margin_ldu / balance.min_margin_ldu)
    else:
        bal_score = 0.0 if balance.tip_hazard else 1.0

    unsupported = len(overhang.unsupported_ids)
    over_score = _clamp01(1.0 - unsupported / n)

    blocked = len(build_order.blocked_ids)
    build_score = _clamp01(1.0 - blocked / n)

    weak_term = _clamp01((1.0 - strength.weak_ratio) / (1.0 - SOFT_WEAK_RATIO))
    mean_term = _clamp01(strength.mean_overlap / SOFT_MEAN_OVERLAP)
    clutch_score = 0.5 * (weak_term + mean_term)

    components = {
        "connectivity": conn_score,
        "collisions": coll_score,
        "balance": bal_score,
        "overhang": over_score,
        "build_order": build_score,
        "clutch": clutch_score,
    }
    weights = {
        "connectivity": W_CONNECTIVITY,
        "collisions": W_COLLISIONS,
        "balance": W_BALANCE,
        "overhang": W_OVERHANG,
        "build_order": W_BUILD_ORDER,
        "clutch": W_CLUTCH,
    }
    score = 100.0 * sum(weights[k] * components[k] for k in weights)

    def lost(key: str) -> float:
        return 100.0 * weights[key] * (1.0 - components[key])

    hard: list[Issue] = []
    soft: list[Issue] = []

    if sections > 1:
        hard.append(
            Issue(
                code="detached_sections",
                severity="hard",
                detail=f"{sections} detached clutch sections (need 1)",
                count=sections,
                impact=lost("connectivity"),
                suggested_action="bridge_sections",
            )
        )
    if collisions > 0:
        hard.append(
            Issue(
                code="collisions",
                severity="hard",
                detail=f"{collisions} intersecting brick pair(s)",
                count=collisions,
                impact=lost("collisions"),
                suggested_action="resolve_collisions",
            )
        )
    if solid_count > 0 and interior_count <= 0:
        hard.append(
            Issue(
                code="not_hollow",
                severity="hard",
                detail="interior is solid-filled (cost / weight bloat)",
                count=solid_count,
                impact=0.0,
                suggested_action="hollow_interior",
            )
        )

    if balance.tip_hazard:
        soft.append(
            Issue(
                code="tip_hazard",
                severity="soft",
                detail=(
                    f"CoM margin {balance.edge_margin_ldu:.1f} LDU "
                    f"< {balance.min_margin_ldu:.1f} required"
                ),
                count=1,
                impact=lost("balance"),
                suggested_action="add_balance_base",
            )
        )
    if unsupported > 0:
        soft.append(
            Issue(
                code="unsupported_pieces",
                severity="soft",
                detail=f"{unsupported} piece(s) unreachable from ground",
                count=unsupported,
                impact=lost("overhang"),
                suggested_action="support_unsupported",
            )
        )
    if blocked > 0:
        soft.append(
            Issue(
                code="mid_air_pieces",
                severity="soft",
                detail=f"{blocked} piece(s) need mid-air placement during assembly",
                count=blocked,
                impact=lost("build_order"),
                suggested_action="support_blocked_pieces",
            )
        )
    if strength.weak_ratio > SOFT_WEAK_RATIO or (
        strength.edge_count > 0 and strength.mean_overlap < SOFT_MEAN_OVERLAP
    ):
        soft.append(
            Issue(
                code="weak_clutch",
                severity="soft",
                detail=(
                    f"{strength.weak_edges}/{strength.edge_count} one-stud joins, "
                    f"mean overlap {strength.mean_overlap:.2f}"
                ),
                count=strength.weak_edges,
                impact=lost("clutch"),
                suggested_action="strengthen_clutch",
            )
        )

    if hard:
        score = min(score, HARD_FAIL_CAP)

    hard.sort(key=lambda i: i.impact, reverse=True)
    soft.sort(key=lambda i: i.impact, reverse=True)

    metrics = {
        "parts": float(len(bricks)),
        "sections": float(sections),
        "collisions": float(collisions),
        "unsupported": float(unsupported),
        "mid_air": float(blocked),
        "weak_edges": float(strength.weak_edges),
        "clutch_edges": float(strength.edge_count),
        "mean_overlap": strength.mean_overlap,
        "hollow_pct": 100.0 * interior_count / solid_count if solid_count else 0.0,
    }

    return ReleaseReport(
        score=score,
        hard_failures=hard,
        soft_issues=soft,
        components=components,
        metrics=metrics,
    )


def format_release_report(report: ReleaseReport) -> str:
    lines = [f"VERDICT: {report.verdict}", "  components:"]
    for key, value in report.components.items():
        lines.append(f"    {key:<13} {value:.2f}")
    if report.issues:
        lines.append("  issues (highest impact first):")
        for issue in report.issues:
            lines.append(
                f"    [{issue.severity}] {issue.code}: {issue.detail} "
                f"(-{issue.impact:.1f} pts -> {issue.suggested_action})"
            )
    else:
        lines.append("  issues: none")
    lines.append(f"  not measured yet: {', '.join(report.unmeasured)}")
    return "\n".join(lines)
