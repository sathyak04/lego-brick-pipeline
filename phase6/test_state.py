"""Phase 6 — agent state / evaluate unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_io import Brick  # noqa: E402
from state import evaluate  # noqa: E402


class TestEvaluate(unittest.TestCase):
    def test_single_brick_is_ready(self) -> None:
        bricks = [Brick("3001.dat", 15, 0.0, -24.0, 0.0)]
        state = evaluate(bricks, interior_count=1, solid_count=1)
        self.assertTrue(state.release.release_ready)
        self.assertEqual(state.collisions, 0)
        self.assertEqual(state.sections, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
