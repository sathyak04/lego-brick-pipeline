"""
Phase 2 legality test suite — collisions + stud connections.

Run:
  python -m unittest phase2.test_legality -v
or:
  python phase2/test_legality.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "phase1"))

from catalog import STUD, get_part  # noqa: E402
from collision import find_collisions  # noqa: E402
from connections import find_stud_faults, local_stud_xz  # noqa: E402
from scene import BrickNode, SceneGraph, root_on_ground, stack_on_studs  # noqa: E402
from transform import Transform  # noqa: E402


def is_legal(scene: SceneGraph) -> bool:
    return not find_collisions(scene) and not find_stud_faults(scene)


def stack(parent_part: str, child_part: str, color_p: int = 14, color_c: int = 4,
          sx: float = 0.0, sz: float = 0.0) -> SceneGraph:
    """Tiny helper: root part on ground, one child stacked on studs."""
    g = SceneGraph()
    p = BrickNode(id="parent", part_id=parent_part, color=color_p)
    c = BrickNode(id="child", part_id=child_part, color=color_c)
    g.add_root(p, root_on_ground(parent_part))
    p.add_child(c, stack_on_studs(child_part, sx=sx, sz=sz))
    return g


# ---------------------------------------------------------------------------
# Transform math
# ---------------------------------------------------------------------------
class TestTransforms(unittest.TestCase):
    def test_identity_compose(self) -> None:
        a = Transform.translation(10, -24, 5)
        w = Transform.identity().compose(a)
        self.assertEqual((w.x, w.y, w.z), (10, -24, 5))

    def test_stack_translation_brick_on_plate(self) -> None:
        # Plate origin at top; brick origin is height_brick above plate top.
        t = stack_on_studs("3001.dat")
        self.assertEqual(t.y, -24)
        self.assertEqual(t.x, 0)
        self.assertEqual(t.z, 0)

    def test_yaw_180_flips_x_and_z(self) -> None:
        t = Transform.yaw_180(20, -24, 10)
        self.assertEqual(t.a, -1)
        self.assertEqual(t.i, -1)
        px, py, pz = t.apply(1, 0, 0)
        self.assertEqual((px, py, pz), (19, -24, 10))  # -X then +translation


# ---------------------------------------------------------------------------
# Stud lattice
# ---------------------------------------------------------------------------
class TestStudLattice(unittest.TestCase):
    def test_1x1_stud_at_origin(self) -> None:
        sites = local_stud_xz(get_part("3005.dat"))
        self.assertEqual(sites, [(0.0, 0.0)])

    def test_2x2_studs_between_origin(self) -> None:
        sites = set(local_stud_xz(get_part("3003.dat")))
        self.assertEqual(
            sites,
            {(-10.0, -10.0), (-10.0, 10.0), (10.0, -10.0), (10.0, 10.0)},
        )

    def test_2x4_has_eight_studs(self) -> None:
        sites = local_stud_xz(get_part("3001.dat"))
        self.assertEqual(len(sites), 8)

    def test_slope_has_two_studs_only(self) -> None:
        sites = local_stud_xz(get_part("3039.dat"))
        self.assertEqual(len(sites), 2)


# ---------------------------------------------------------------------------
# LEGAL builds — must pass collisions AND studs
# ---------------------------------------------------------------------------
class TestLegalBuilds(unittest.TestCase):
    def test_plate_with_brick(self) -> None:
        g = stack("3020.dat", "3001.dat")
        self.assertEqual(find_collisions(g), [])
        self.assertEqual(find_stud_faults(g), [])
        self.assertTrue(is_legal(g))

    def test_brick_with_brick(self) -> None:
        g = stack("3001.dat", "3001.dat")
        self.assertTrue(is_legal(g))

    def test_2x2_with_1x1_on_corner_stud(self) -> None:
        g = stack("3003.dat", "3005.dat", sx=-0.5, sz=-0.5)
        self.assertTrue(is_legal(g))

    def test_2x2_with_1x1_all_four_corners(self) -> None:
        for sx, sz in [(-0.5, -0.5), (-0.5, 0.5), (0.5, -0.5), (0.5, 0.5)]:
            with self.subTest(sx=sx, sz=sz):
                g = stack("3003.dat", "3005.dat", sx=sx, sz=sz)
                self.assertTrue(is_legal(g), f"1x1 at ({sx},{sz}) should be legal")

    def test_2x4_covered_by_two_2x2(self) -> None:
        g = SceneGraph()
        base = BrickNode(id="base", part_id="3020.dat", color=14)
        a = BrickNode(id="a", part_id="3003.dat", color=4)
        b = BrickNode(id="b", part_id="3003.dat", color=1)
        g.add_root(base, root_on_ground("3020.dat"))
        base.add_child(a, stack_on_studs("3003.dat", sx=-1.0))
        base.add_child(b, stack_on_studs("3003.dat", sx=1.0))
        self.assertTrue(is_legal(g))

    def test_2x4_with_two_slopes(self) -> None:
        g = SceneGraph()
        wall = BrickNode(id="wall", part_id="3001.dat", color=4)
        s_l = BrickNode(id="s_l", part_id="3039.dat", color=1)
        s_r = BrickNode(id="s_r", part_id="3039.dat", color=1)
        g.add_root(wall, root_on_ground("3001.dat"))
        wall.add_child(s_l, stack_on_studs("3039.dat", sx=-1.0))
        wall.add_child(s_r, stack_on_studs("3039.dat", sx=1.0))
        self.assertTrue(is_legal(g))

    def test_plate_brick_plate_tower(self) -> None:
        g = SceneGraph()
        p = BrickNode(id="p", part_id="3020.dat", color=14)
        b = BrickNode(id="b", part_id="3003.dat", color=4)
        t = BrickNode(id="t", part_id="3005.dat", color=25)
        c = BrickNode(id="c", part_id="3024.dat", color=0)
        g.add_root(p, root_on_ground("3020.dat"))
        p.add_child(b, stack_on_studs("3003.dat", sx=-1.0))
        b.add_child(t, stack_on_studs("3005.dat", sx=-0.5, sz=-0.5))
        t.add_child(c, stack_on_studs("3024.dat"))
        self.assertTrue(is_legal(g))

    def test_side_by_side_plates_touch_not_collide(self) -> None:
        g = SceneGraph()
        a = BrickNode(id="a", part_id="3020.dat", color=14)
        b = BrickNode(id="b", part_id="3020.dat", color=15)
        g.add_root(a, root_on_ground("3020.dat", sx=0.0))
        g.add_root(b, root_on_ground("3020.dat", sx=4.0))  # edge-touch
        self.assertEqual(find_collisions(g), [])
        self.assertTrue(is_legal(g))


# ---------------------------------------------------------------------------
# ILLEGAL — off-stud (may have zero collisions)
# ---------------------------------------------------------------------------
class TestOffStudIllegal(unittest.TestCase):
    def test_1x1_centered_on_2x2_is_between_studs(self) -> None:
        g = stack("3003.dat", "3005.dat", sx=0.0, sz=0.0)
        self.assertEqual(find_collisions(g), [], "should not collide")
        faults = find_stud_faults(g)
        self.assertTrue(faults, "1x1 at 2x2 center must fail stud check")
        self.assertFalse(is_legal(g))

    def test_1x2_centered_on_2x4_plate_straddles_rows(self) -> None:
        # depth-1 brick at sz=0 sits between the plate's two stud rows
        g = stack("3020.dat", "3004.dat", sx=0.0, sz=0.0)
        faults = find_stud_faults(g)
        self.assertTrue(faults)
        self.assertFalse(is_legal(g))

    def test_1x2_on_front_row_of_plate_is_legal(self) -> None:
        g = stack("3020.dat", "3004.dat", sx=0.0, sz=-0.5)
        self.assertTrue(is_legal(g))

    def test_half_stud_shift_off_grid(self) -> None:
        g = stack("3020.dat", "3001.dat", sx=0.5)  # half-stud slide
        self.assertTrue(find_stud_faults(g))
        self.assertFalse(is_legal(g))


# ---------------------------------------------------------------------------
# ILLEGAL — collisions
# ---------------------------------------------------------------------------
class TestCollisionIllegal(unittest.TestCase):
    def test_duplicate_in_same_slot(self) -> None:
        g = SceneGraph()
        p = BrickNode(id="p", part_id="3020.dat", color=14)
        a = BrickNode(id="a", part_id="3001.dat", color=4)
        b = BrickNode(id="b", part_id="3001.dat", color=2)
        g.add_root(p, root_on_ground("3020.dat"))
        p.add_child(a, stack_on_studs("3001.dat"))
        p.add_child(b, stack_on_studs("3001.dat"))
        hits = find_collisions(g)
        self.assertTrue(hits)
        self.assertTrue(any({h.a_id, h.b_id} == {"a", "b"} for h in hits))
        self.assertFalse(is_legal(g))

    def test_side_jab_into_neighbor(self) -> None:
        g = SceneGraph()
        p = BrickNode(id="p", part_id="3020.dat", color=14)
        wall = BrickNode(id="wall", part_id="3001.dat", color=4)
        jab = BrickNode(id="jab", part_id="3004.dat", color=25)
        g.add_root(p, root_on_ground("3020.dat"))
        p.add_child(wall, stack_on_studs("3001.dat"))
        p.add_child(jab, stack_on_studs("3004.dat", sx=1.0))
        self.assertTrue(find_collisions(g))
        self.assertFalse(is_legal(g))

    def test_sinker_half_height(self) -> None:
        g = SceneGraph()
        p = BrickNode(id="p", part_id="3020.dat", color=14)
        good = BrickNode(id="good", part_id="3003.dat", color=2)
        sink = BrickNode(id="sink", part_id="3003.dat", color=0)
        g.add_root(p, root_on_ground("3020.dat"))
        p.add_child(good, stack_on_studs("3003.dat"))
        p.add_child(sink, Transform.translation(0.0, -12.0, 0.0))  # half rise
        self.assertTrue(find_collisions(g))
        self.assertFalse(is_legal(g))

    def test_two_plates_overlapping(self) -> None:
        g = SceneGraph()
        a = BrickNode(id="a", part_id="3020.dat", color=14)
        b = BrickNode(id="b", part_id="3020.dat", color=15)
        g.add_root(a, root_on_ground("3020.dat", sx=0.0))
        g.add_root(b, root_on_ground("3020.dat", sx=2.0))  # 2-stud overlap
        self.assertTrue(find_collisions(g))
        self.assertFalse(is_legal(g))


# ---------------------------------------------------------------------------
# Spatial hash (Phase 2 Step 4)
# ---------------------------------------------------------------------------
class TestSpatialHash(unittest.TestCase):
    def _pair_set(self, hits):
        return {frozenset((h.a_id, h.b_id)) for h in hits}

    def test_hash_matches_bruteforce_on_overlap(self) -> None:
        from collision import find_collisions_bruteforce

        g = SceneGraph()
        p = BrickNode(id="p", part_id="3020.dat", color=14)
        a = BrickNode(id="a", part_id="3001.dat", color=4)
        b = BrickNode(id="b", part_id="3001.dat", color=2)
        g.add_root(p, root_on_ground("3020.dat"))
        p.add_child(a, stack_on_studs("3001.dat"))
        p.add_child(b, stack_on_studs("3001.dat"))
        self.assertEqual(
            self._pair_set(find_collisions(g)),
            self._pair_set(find_collisions_bruteforce(g)),
        )

    def test_hash_matches_bruteforce_on_legal(self) -> None:
        from collision import find_collisions_bruteforce

        g = stack("3020.dat", "3001.dat")
        self.assertEqual(find_collisions(g), [])
        self.assertEqual(find_collisions_bruteforce(g), [])

    def test_hash_matches_bruteforce_scattered_grid(self) -> None:
        """Many non-overlapping 1x1s — hash must not invent collisions."""
        from collision import find_collisions_bruteforce

        g = SceneGraph()
        for i in range(5):
            for j in range(5):
                n = BrickNode(id=f"b{i}_{j}", part_id="3005.dat", color=4)
                g.add_root(n, root_on_ground("3005.dat", sx=float(i), sz=float(j)))
        self.assertEqual(
            self._pair_set(find_collisions(g)),
            self._pair_set(find_collisions_bruteforce(g)),
        )
        self.assertEqual(find_collisions(g), [])

    def test_hash_finds_distant_duplicate_pair(self) -> None:
        from collision import find_collisions_bruteforce

        g = SceneGraph()
        # Far away cluster with an intentional overlap
        a = BrickNode(id="a", part_id="3005.dat", color=4)
        b = BrickNode(id="b", part_id="3005.dat", color=1)
        g.add_root(a, root_on_ground("3005.dat", sx=20.0, sz=20.0))
        g.add_root(b, root_on_ground("3005.dat", sx=20.0, sz=20.0))  # same cell
        self.assertEqual(
            self._pair_set(find_collisions(g)),
            self._pair_set(find_collisions_bruteforce(g)),
        )
        self.assertTrue(find_collisions(g))


# ---------------------------------------------------------------------------
# Runner with summary table
# ---------------------------------------------------------------------------
def _run() -> None:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 60)
    print(
        f"SUMMARY: {result.testsRun} tests, "
        f"{len(result.failures)} failed, "
        f"{len(result.errors)} errors, "
        f"{len(result.skipped)} skipped"
    )
    if result.wasSuccessful():
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    _run()
