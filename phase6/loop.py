"""
Phase 6 — deterministic release-readiness hill-climber.

Blueprint: use Phase 5 as an automated feedback loop — apply a suggested
fix, re-score, keep if the release score rises without breaking hard gates.

No LLM yet. Action choice is scorecard.next_action, falling back to the
registry order when the suggested action is not implemented.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from actions import ACTIONS  # noqa: E402
from state import ModelState, evaluate  # noqa: E402


@dataclass
class RoundLog:
    action: str
    accepted: bool
    score_before: float
    score_after: float
    parts_added: int
    detail: str = ""


@dataclass
class ImproveResult:
    initial: ModelState
    final: ModelState
    log: list[RoundLog] = field(default_factory=list)

    @property
    def accepted(self) -> int:
        return sum(1 for r in self.log if r.accepted)

    @property
    def delta(self) -> float:
        return self.final.score - self.initial.score


def _candidate_actions(state: ModelState) -> list[str]:
    """Ordered action names to try this round (highest-impact first)."""
    ordered: list[str] = []
    seen: set[str] = set()
    mapping = {
        "detached_sections": "bridge_sections",
        "collisions": "resolve_collisions",
        "tip_hazard": "add_balance_base",
        "unsupported_pieces": "support_unsupported",
        # mid_air_pieces: no registered action — cavity/shell mid-air needs a
        # real instruction strategy, not stud columns stuffing the hollow.
        "weak_clutch": "strengthen_clutch",
        "part_count_bloat": "merge_bloat",
        "shear_columns": "stagger_seams",
    }
    for issue in state.release.issues:
        action = mapping.get(issue.code)
        if action and action in ACTIONS and action not in seen:
            ordered.append(action)
            seen.add(action)
    return ordered


def improve_release(
    state: ModelState,
    *,
    max_rounds: int = 20,
    verbose: bool = False,
) -> ImproveResult:
    """Hill-climb until READY, no progress, or max_rounds."""
    current = state
    log: list[RoundLog] = []

    for rnd in range(max_rounds):
        if current.release.release_ready:
            if verbose:
                print(f"  round {rnd}: READY ({current.score:.1f})")
            break

        actions = _candidate_actions(current)
        if not actions:
            if verbose:
                print(f"  round {rnd}: no implemented action for issues")
            break

        progressed = False
        for action in actions:
            fn = ACTIONS[action]
            before = current.score
            new_bricks, n_added = fn(current.bricks)
            if n_added <= 0:
                log.append(
                    RoundLog(
                        action=action,
                        accepted=False,
                        score_before=before,
                        score_after=before,
                        parts_added=0,
                        detail="noop",
                    )
                )
                if verbose:
                    print(f"  round {rnd}: {action} noop — try next")
                continue

            candidate = evaluate(
                new_bricks,
                interior_count=current.interior_count,
                solid_count=current.solid_count,
            )

            if not candidate.hard_ok and current.hard_ok:
                log.append(
                    RoundLog(
                        action=action,
                        accepted=False,
                        score_before=before,
                        score_after=candidate.score,
                        parts_added=n_added,
                        detail="hard-gate regression",
                    )
                )
                if verbose:
                    print(
                        f"  round {rnd}: {action} +{n_added} rejected "
                        f"(hard gate {candidate.sections}sec/"
                        f"{candidate.collisions}col)"
                    )
                continue

            if candidate.score > before + 1e-6:
                log.append(
                    RoundLog(
                        action=action,
                        accepted=True,
                        score_before=before,
                        score_after=candidate.score,
                        parts_added=n_added,
                    )
                )
                if verbose:
                    print(
                        f"  round {rnd}: {action} +{n_added} "
                        f"{before:.1f} -> {candidate.score:.1f} KEEP"
                    )
                current = candidate
                progressed = True
                break

            log.append(
                RoundLog(
                    action=action,
                    accepted=False,
                    score_before=before,
                    score_after=candidate.score,
                    parts_added=n_added,
                    detail="no score gain",
                )
            )
            if verbose:
                print(
                    f"  round {rnd}: {action} +{n_added} "
                    f"{before:.1f} -> {candidate.score:.1f} revert — try next"
                )

        if not progressed:
            if verbose:
                print(f"  round {rnd}: no improving action — stop")
            break

    return ImproveResult(initial=state, final=current, log=log)
