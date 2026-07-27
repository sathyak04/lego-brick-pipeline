"""
Phase 4 — Model-agnostic clutch structure (no overhang pillars).

Hard rule: never add bricks in outside-reachable air (overhangs).
Only fill enclosed cavities; seal tiny cracks; interlock inside the solid.

Pipeline:
  1) fill_enclosed_cavities — outside flood-fill; fill unreachable empties
  2) close_surface_cracks — morphological close, capped to dilate(S,1)
  3) choose_column_staples — Kruskal 1x2 staples on existing cells
  4) pack_staples_then_merge — large bricks for clutch power
  5) repair_clutch_cuts — force 1x2 across in-solid clutch cuts
  6) last resort — dilate at most 2 studs if still multiple 6-CCs
"""

from __future__ import annotations

import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5"))

from voxelize import Voxel  # noqa: E402
from greedy import (  # noqa: E402
    IDENTITY,
    YAW_90,
    Placement,
    consolidate_voxels,
    placements_to_bricks,
)
from connectivity import check_connectivity  # noqa: E402

NEIGH6 = (
    (1, 0, 0), (-1, 0, 0),
    (0, 1, 0), (0, -1, 0),
    (0, 0, 1), (0, 0, -1),
)


def _as_set(voxels: list[Voxel]) -> set[tuple[int, int, int]]:
    return {(v.ix, v.iy, v.iz) for v in voxels}


def _to_voxels(cells: set[tuple[int, int, int]]) -> list[Voxel]:
    return [Voxel(ix, iy, iz) for ix, iy, iz in sorted(cells)]


def _dilate(cells: set[tuple[int, int, int]], rounds: int = 1) -> set[tuple[int, int, int]]:
    cur = set(cells)
    for _ in range(rounds):
        nxt = set(cur)
        for x, y, z in cur:
            for dx, dy, dz in NEIGH6:
                nxt.add((x + dx, y + dy, z + dz))
        cur = nxt
    return cur


def _erode(cells: set[tuple[int, int, int]]) -> set[tuple[int, int, int]]:
    return {
        (x, y, z)
        for x, y, z in cells
        if all((x + dx, y + dy, z + dz) in cells for dx, dy, dz in NEIGH6)
    }


def count_6(cells: set[tuple[int, int, int]]) -> int:
    seen: set[tuple[int, int, int]] = set()
    n = 0
    for start in cells:
        if start in seen:
            continue
        n += 1
        q = deque([start])
        seen.add(start)
        while q:
            x, y, z = q.popleft()
            for dx, dy, dz in NEIGH6:
                t = (x + dx, y + dy, z + dz)
                if t in cells and t not in seen:
                    seen.add(t)
                    q.append(t)
    return n


def fill_enclosed_cavities(
    solid: set[tuple[int, int, int]],
) -> set[tuple[int, int, int]]:
    """
    Fill empty cells that cannot be reached from outside the bbox.

    Outside-reachable empty = overhang / exterior air → NEVER filled.
    Unreachable empty = enclosed cavity → filled for structure.
    """
    if not solid:
        return set()

    ix0 = min(c[0] for c in solid) - 1
    ix1 = max(c[0] for c in solid) + 1
    iy0 = min(c[1] for c in solid) - 1
    iy1 = max(c[1] for c in solid) + 1
    iz0 = min(c[2] for c in solid) - 1
    iz1 = max(c[2] for c in solid) + 1

    # Flood empty from a corner outside the solid
    start = (ix0, iy0, iz0)
    outside: set[tuple[int, int, int]] = set()
    q: deque[tuple[int, int, int]] = deque([start])
    outside.add(start)
    while q:
        x, y, z = q.popleft()
        for dx, dy, dz in NEIGH6:
            n = (x + dx, y + dy, z + dz)
            nx, ny, nz = n
            if not (ix0 <= nx <= ix1 and iy0 <= ny <= iy1 and iz0 <= nz <= iz1):
                continue
            if n in solid or n in outside:
                continue
            outside.add(n)
            q.append(n)

    filled = set(solid)
    for x in range(ix0 + 1, ix1):
        for y in range(iy0 + 1, iy1):
            for z in range(iz0 + 1, iz1):
                c = (x, y, z)
                if c not in solid and c not in outside:
                    filled.add(c)
    return filled


def close_surface_cracks(
    cells: set[tuple[int, int, int]],
    *,
    rounds: int = 2,
) -> set[tuple[int, int, int]]:
    """
    Morphological close for 1-cell mesh cracks.
    Cap: result ⊆ dilate(original, 1) ∪ original — no long exterior towers.
    """
    if not cells:
        return cells
    original = set(cells)
    cur = set(cells)
    for _ in range(rounds):
        cur = original | _erode(_dilate(cur, 1))
    cap = _dilate(original, rounds=1) | original
    return cur & cap


def keep_near_original(
    original: set[tuple[int, int, int]],
    cells: set[tuple[int, int, int]],
) -> set[tuple[int, int, int]]:
    """
    Drop any non-original cell that is not face-adjacent to the original
    solid. Allows a 1-ring dilate shell; blocks deep overhang column fills.
    """
    out: set[tuple[int, int, int]] = set()
    for c in cells:
        if c in original:
            out.add(c)
            continue
        x, y, z = c
        if any((x + dx, y + dy, z + dz) in original for dx, dy, dz in NEIGH6):
            out.add(c)
    return out


def choose_column_staples(
    cells: set[tuple[int, int, int]],
) -> list[tuple[int, tuple[int, int], tuple[int, int]]]:
    """
    Kruskal on columns with cell capacity 1. Then a second pass tries any
    remaining adjacent column-component pairs on free shared layers.
    """
    cols = {(ix, iz) for ix, _iy, iz in cells}
    parent = {c: c for c in cols}
    rank = {c: 0 for c in cols}
    heights: dict[tuple[int, int], set[int]] = defaultdict(set)
    for ix, iy, iz in cells:
        heights[(ix, iz)].add(iy)

    def find(a: tuple[int, int]) -> tuple[int, int]:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: tuple[int, int], b: tuple[int, int]) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1
        return True

    used: set[tuple[int, int, int]] = set()
    staples: list[tuple[int, tuple[int, int], tuple[int, int]]] = []

    edges: list[
        tuple[int, tuple[int, int], tuple[int, int], tuple[int, int, int], tuple[int, int, int]]
    ] = []
    for ix, iy, iz in cells:
        for dx, dz in ((1, 0), (0, 1)):
            n = (ix + dx, iy, iz + dz)
            if n not in cells:
                continue
            edges.append((iy, (ix, iz), (n[0], n[2]), (ix, iy, iz), n))
    edges.sort(key=lambda e: e[0])

    for iy, ca, cb, cell_a, cell_b in edges:
        if find(ca) == find(cb):
            continue
        if cell_a in used or cell_b in used:
            continue
        if not union(ca, cb):
            continue
        used.add(cell_a)
        used.add(cell_b)
        staples.append((iy, ca, cb))

    # Second pass: remaining adjacent column pairs, any free shared layer
    col_list = list(cols)
    changed = True
    while changed:
        changed = False
        for ca in col_list:
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cb = (ca[0] + dx, ca[1] + dz)
                if cb not in cols:
                    continue
                if find(ca) == find(cb):
                    continue
                shared = sorted(heights[ca] & heights[cb])
                for iy in shared:
                    cell_a = (ca[0], iy, ca[1])
                    cell_b = (cb[0], iy, cb[1])
                    if cell_a in used or cell_b in used:
                        continue
                    if not union(ca, cb):
                        break
                    used.add(cell_a)
                    used.add(cell_b)
                    staples.append((iy, ca, cb))
                    changed = True
                    break
    return staples


def pack_staples_then_merge(
    cells: set[tuple[int, int, int]],
    staples: list[tuple[int, tuple[int, int], tuple[int, int]]],
    color: int,
) -> list[Placement]:
    by_layer: dict[int, set[tuple[int, int]]] = defaultdict(set)
    for ix, iy, iz in cells:
        by_layer[iy].add((ix, iz))

    out: list[Placement] = []
    for iy, a, b in staples:
        (x1, z1), (x2, z2) = a, b
        if (x1, z1) not in by_layer[iy] or (x2, z2) not in by_layer[iy]:
            continue
        if z1 == z2 and abs(x1 - x2) == 1:
            out.append(
                Placement("3004.dat", color, min(x1, x2), iy, z1, 2, 1, IDENTITY)
            )
            by_layer[iy].discard((x1, z1))
            by_layer[iy].discard((x2, z2))
        elif x1 == x2 and abs(z1 - z2) == 1:
            out.append(
                Placement("3004.dat", color, x1, iy, min(z1, z2), 1, 2, YAW_90)
            )
            by_layer[iy].discard((x1, z1))
            by_layer[iy].discard((x2, z2))

    leftover = [
        Voxel(ix, iy, iz) for iy, layer in by_layer.items() for ix, iz in layer
    ]
    out.extend(consolidate_voxels(leftover, color=color, stagger=True))
    return out


def pack_staples_and_1x1(
    cells: set[tuple[int, int, int]],
    staples: list[tuple[int, tuple[int, int], tuple[int, int]]],
    color: int,
) -> list[Placement]:
    consumed: set[tuple[int, int, int]] = set()
    out: list[Placement] = []
    for iy, a, b in staples:
        (x1, z1), (x2, z2) = a, b
        ca, cb = (x1, iy, z1), (x2, iy, z2)
        if ca not in cells or cb not in cells:
            continue
        if ca in consumed or cb in consumed:
            continue
        if z1 == z2 and abs(x1 - x2) == 1:
            out.append(
                Placement("3004.dat", color, min(x1, x2), iy, z1, 2, 1, IDENTITY)
            )
        elif x1 == x2 and abs(z1 - z2) == 1:
            out.append(
                Placement("3004.dat", color, x1, iy, min(z1, z2), 1, 2, YAW_90)
            )
        else:
            continue
        consumed.add(ca)
        consumed.add(cb)
    for ix, iy, iz in sorted(cells):
        if (ix, iy, iz) in consumed:
            continue
        out.append(Placement("3005.dat", color, ix, iy, iz, 1, 1, IDENTITY))
    return out


def repair_clutch_cuts(
    cells: set[tuple[int, int, int]],
    color: int,
) -> list[Placement]:
    """
    Staple tree + prefer large-brick merge when it preserves section count;
    otherwise staples + 1x1 (still in-solid only).
    """
    staples = choose_column_staples(cells)
    merged = pack_staples_then_merge(cells, staples, color)
    m_sec = check_connectivity(placements_to_bricks(merged)).section_count
    if m_sec <= 1:
        return merged

    ones = pack_staples_and_1x1(cells, staples, color)
    o_sec = check_connectivity(placements_to_bricks(ones)).section_count
    if o_sec < m_sec:
        return ones
    return merged


def _placement_cells(p: Placement) -> set[tuple[int, int, int]]:
    return {
        (x, p.iy, z)
        for x in range(p.ix, p.ix + p.w)
        for z in range(p.iz, p.iz + p.d)
    }


def _contact_clutch_staples(
    island_vox: set[tuple[int, int, int]],
    main_vox: set[tuple[int, int, int]],
    walkable: set[tuple[int, int, int]],
    cells: set[tuple[int, int, int]],
) -> list[tuple[int, tuple[int, int], tuple[int, int]]]:
    """
    Thin clutch fixes at island↔main contact:
      1) same-layer 1x2 covering both cells (one brick),
      2) else a 1x2 on the layer above/below spanning both columns.
    """
    forced: list[tuple[int, tuple[int, int], tuple[int, int]]] = []
    seen: set[tuple[int, tuple[int, int], tuple[int, int]]] = set()
    for ix, iy, iz in island_vox:
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            m = (ix + dx, iy, iz + dz)
            if m not in main_vox:
                continue
            mx, _, mz = m
            # Prefer same-layer staple (joins into one brick)
            key = (iy, (min(ix, mx), min(iz, mz)), (max(ix, mx), max(iz, mz)))
            if key not in seen:
                seen.add(key)
                forced.append((iy, (ix, iz), (mx, mz)))
            for by in (iy + 1, iy - 1):
                a, b = (ix, by, iz), (mx, by, mz)
                if a in walkable and b in walkable:
                    cells.add(a)
                    cells.add(b)
                    k2 = (by, (min(ix, mx), min(iz, mz)), (max(ix, mx), max(iz, mz)))
                    if k2 not in seen:
                        seen.add(k2)
                        forced.append((by, (ix, iz), (mx, mz)))
                    break
    return forced


def tie_islands_through_solid(
    keep: set[tuple[int, int, int]],
    solid: set[tuple[int, int, int]],
    color: int,
    *,
    max_rounds: int = 25,
    allow_dilate: int = 0,
    max_fill_ratio: float = 0.55,
) -> tuple[set[tuple[int, int, int]], list[Placement], int]:
    """
    Connect clutch islands with thin in-solid paths (beams), not solid fill.

    - Walkable = solid (optional 1-cell dilate for mesh cracks only).
    - Each round adds shortest paths from main → islands (no full-column pin).
    - Stops if voxel count would exceed max_fill_ratio * |solid|.
    """
    walkable = set(solid)
    if allow_dilate > 0:
        walkable = _dilate(solid, allow_dilate) | solid

    cells = set(keep) & walkable
    # Headroom for thin beam ties; hard cap so we never solid-fill.
    budget = min(len(solid), max(len(cells) + 350, int(max_fill_ratio * len(solid))))
    print(
        f"    tie budget={budget} ({100 * budget / max(len(solid), 1):.0f}% of solid), "
        f"start={len(cells)}"
    )
    staples = choose_column_staples(cells)
    placements = pack_staples_then_merge(cells, staples, color)
    best_sections = 10**9
    best_cells = set(cells)
    best_placements = list(placements)

    for _round in range(max_rounds):
        bricks = placements_to_bricks(placements)
        report = check_connectivity(bricks)
        sections = report.section_count
        print(
            f"    tie round {_round}: sections={sections} "
            f"voxels={len(cells)} ({100 * len(cells) / max(len(solid), 1):.0f}%)"
        )
        if sections < best_sections:
            best_sections = sections
            best_cells = set(cells)
            best_placements = list(placements)
        if sections <= 1:
            break

        main_ids = set(report.components[report.largest_component_id])
        main_vox: set[tuple[int, int, int]] = set()
        # One voxel seed per island component (keeps paths thin)
        island_seeds: list[tuple[int, int, int]] = []
        island_vox: set[tuple[int, int, int]] = set()
        for cid, members in enumerate(report.components):
            if cid == report.largest_component_id:
                for i in members:
                    main_vox |= _placement_cells(placements[i])
                continue
            seed_cells: set[tuple[int, int, int]] = set()
            for i in members:
                seed_cells |= _placement_cells(placements[i])
            island_vox |= seed_cells
            # centroid-ish: first cell
            island_seeds.append(next(iter(seed_cells)))

        prev_map: dict[tuple[int, int, int], tuple[int, int, int] | None] = {
            s: None for s in main_vox if s in walkable
        }
        q: deque[tuple[int, int, int]] = deque(prev_map.keys())
        hit: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        while q and len(hit) < len(island_seeds):
            cur = q.popleft()
            if cur in island_vox and cur not in hit:
                hit[cur] = cur
                continue
            x, y, z = cur
            for dx, dy, dz in NEIGH6:
                n = (x + dx, y + dy, z + dz)
                if n not in walkable or n in prev_map:
                    continue
                prev_map[n] = cur
                q.append(n)

        if not hit:
            print("    (no walkable path to islands; trying contact staples)")
            forced = _contact_clutch_staples(island_vox, main_vox, walkable, cells)
            if not forced:
                break
            staples = forced + choose_column_staples(cells)
            placements = pack_staples_then_merge(cells, staples, color)
            continue

        # Trace paths as stacked beams (y and y+1) — a single-layer 1x1
        # run has no stud–tube clutch between neighbors.
        before = len(cells)
        path_cells: set[tuple[int, int, int]] = set()
        for end in hit:
            cur2: tuple[int, int, int] | None = end
            while cur2 is not None:
                path_cells.add(cur2)
                cur2 = prev_map.get(cur2)
        for ix, iy, iz in list(path_cells):
            if len(cells) >= budget:
                break
            cells.add((ix, iy, iz))
            above = (ix, iy + 1, iz)
            if above in walkable and len(cells) < budget:
                cells.add(above)
            below = (ix, iy - 1, iz)
            if below in walkable and len(cells) < budget:
                cells.add(below)

        # Clutch fix: vertical bridges + same-layer 1x2 staples at island↔main cuts.
        forced = _contact_clutch_staples(island_vox, main_vox, walkable, cells)
        for ix, iy, iz in list(path_cells):
            for dx, dz in ((1, 0), (0, 1)):
                n = (ix + dx, iy, iz + dz)
                if n not in cells and n not in path_cells:
                    continue
                # Same-layer long-beam staple
                forced.append((iy, (ix, iz), (n[0], n[2])))
                by = iy + 1
                a, b = (ix, by, iz), (n[0], by, n[2])
                if a in walkable and b in walkable and len(cells) < budget:
                    cells.add(a)
                    cells.add(b)
                    forced.append((by, (ix, iz), (n[0], n[2])))

        if len(cells) > budget:
            cells = set(best_cells)
            placements = list(best_placements)
            break

        staples = forced + choose_column_staples(cells)
        placements = pack_staples_then_merge(cells, staples, color)
        new_sec = check_connectivity(placements_to_bricks(placements)).section_count
        print(f"    after paths/staples: sections={new_sec} voxels={len(cells)}")
        if new_sec < best_sections:
            best_sections = new_sec
            best_cells = set(cells)
            best_placements = list(placements)
        elif new_sec > best_sections + 2:
            cells = set(best_cells)
            placements = list(best_placements)
            break
        elif len(cells) == before and new_sec >= sections:
            # No progress on this round — try contact staples once more then stop
            forced2 = _contact_clutch_staples(island_vox, main_vox, walkable, cells)
            if not forced2:
                break
            placements = pack_staples_then_merge(
                cells, forced2 + choose_column_staples(cells), color
            )
            new_sec2 = check_connectivity(placements_to_bricks(placements)).section_count
            if new_sec2 < best_sections:
                best_sections = new_sec2
                best_cells = set(cells)
                best_placements = list(placements)
            else:
                break

    cells = set(best_cells)
    placements = list(best_placements)
    sections = check_connectivity(placements_to_bricks(placements)).section_count
    print(
        f"    final tie: sections={sections} "
        f"voxels={len(cells)} ({100 * len(cells) / max(len(solid), 1):.0f}%)"
    )
    return cells, placements, sections


@dataclass(frozen=True)
class StructureReport:
    placements: list[Placement]
    voxels: list[Voxel]
    section_count: int
    voxels_added: int
    dilate_used: int
    six_cc: int

    @property
    def verdict(self) -> str:
        if self.section_count <= 1:
            return "PASS - single clutch section"
        return f"FAIL - {self.section_count} detached sections (in-solid limit)"


def build_connected_structure(
    solid: list[Voxel],
    *,
    color: int = 14,
    close_rounds: int = 2,
    max_dilate: int = 2,
) -> StructureReport:
    """
    Model-agnostic structure pass. Never fills overhang air via column gaps.
    Dilate (at most max_dilate) only if multiple 6-connected components remain;
    dilate shell is clipped to face-adjacent ring of the original solid.
    """
    original = _as_set(solid)
    n0 = len(original)

    cells = fill_enclosed_cavities(original)
    cells = close_surface_cracks(cells, rounds=close_rounds)
    cells = keep_near_original(original, cells) | original

    dilate_used = 0
    while count_6(cells) > 1 and dilate_used < max_dilate:
        dilate_used += 1
        cells = _dilate(original, dilate_used)
        cells = fill_enclosed_cavities(cells)
        cells = close_surface_cracks(cells, rounds=1)
        cells = keep_near_original(original, cells) | original

    placements = repair_clutch_cuts(cells, color)
    sections = check_connectivity(placements_to_bricks(placements)).section_count

    return StructureReport(
        placements=placements,
        voxels=_to_voxels(cells),
        section_count=sections,
        voxels_added=len(cells) - n0,
        dilate_used=dilate_used,
        six_cc=count_6(cells),
    )


# Back-compat alias used by older demos
def build_fully_connected(
    solid: list[Voxel],
    *,
    color: int = 14,
    close_rounds: int = 2,
) -> tuple[list[Placement], list[Voxel], int]:
    r = build_connected_structure(solid, color=color, close_rounds=close_rounds)
    return r.placements, r.voxels, r.section_count


def thicken_beams(
    lattice: set[tuple[int, int, int]],
    solid: set[tuple[int, int, int]],
    *,
    size: int = 2,
) -> set[tuple[int, int, int]]:
    """Expand each lattice cell to a size×size footprint (in-solid only)."""
    out: set[tuple[int, int, int]] = set()
    for ix, iy, iz in lattice:
        for dx in range(size):
            for dz in range(size):
                c = (ix + dx, iy, iz + dz)
                if c in solid:
                    out.add(c)
    return out


def _sparse_column_beams(
    solid_set: set[tuple[int, int, int]],
    shell_set: set[tuple[int, int, int]],
    *,
    stride: int,
    beam_size: int,
) -> set[tuple[int, int, int]]:
    """
    A few vertical 2×2 beams inside the hollow — NOT a solid fill.

    1) Pick sparse (ix, iz) centers on a stride grid in the interior.
    2) Fill those columns through the solid (1-cell thick).
    3) Thicken to beam_size×beam_size.
    Never pin after thicken (that re-densifies).
    """
    interior = solid_set - shell_set
    if not interior:
        return set()
    ixs = [ix for ix, _, _ in interior]
    izs = [iz for _, _, iz in interior]
    ix0, iz0 = min(ixs), min(izs)

    centers: set[tuple[int, int]] = set()
    for ix, _iy, iz in interior:
        if (ix - ix0) % stride == 0 and (iz - iz0) % stride == 0:
            centers.add((ix, iz))

    # Thin columns first
    thin: set[tuple[int, int, int]] = set()
    for ix, iy, iz in solid_set:
        if (ix, iz) in centers:
            thin.add((ix, iy, iz))

    return thicken_beams(thin, solid_set, size=beam_size)


def reinforce_hollow_shell(
    solid: list[Voxel],
    *,
    color: int = 15,
    stride: int = 7,
    floor_every: int = 0,
    beam_size: int = 2,
    max_fill_ratio: float = 0.42,
    max_rounds: int = 15,
) -> tuple[set[tuple[int, int, int]], list[Placement], int, set[tuple[int, int, int]]]:
    """
    Hollow shell + a few real 2×2 column beams + clutch staples.

    Hard fill cap. No floor slabs. No post-thicken pin (avoids solid red fill).
    Returns (cells, placements, section_count, shell_set).
    """
    from scaffold import shell_plus_scaffold

    solid_set = _as_set(solid)
    shell, _interior, _sc, _ = shell_plus_scaffold(
        solid, stride=99, floor_every=0, belt_every=0, pin_columns=False
    )
    shell_set = _as_set(shell)

    budget = int(max_fill_ratio * len(solid_set))
    # Always keep full shell even if over ratio (silhouette); beams use remainder
    beam_budget = max(0, budget - len(shell_set))

    beams = _sparse_column_beams(
        solid_set, shell_set, stride=stride, beam_size=beam_size
    )
    if len(beams) > beam_budget:
        # Keep whole columns preferentially: sort by column, take until budget
        by_col: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
        for ix, iy, iz in beams:
            by_col[(ix // beam_size * beam_size, iz // beam_size * beam_size)].append(
                (ix, iy, iz)
            )
        beams = set()
        for _col, cells_in_col in sorted(by_col.items()):
            if len(beams) >= beam_budget:
                break
            for c in cells_in_col:
                if len(beams) >= beam_budget:
                    break
                beams.add(c)

    cells = shell_set | beams
    print(
        f"  reinforce: shell={len(shell_set)} beams={len(beams)} "
        f"kept={len(cells)}/{len(solid_set)} "
        f"({100 * len(cells) / len(solid_set):.0f}%) "
        f"budget={budget} (beam_budget={beam_budget})"
    )

    staples = choose_column_staples(cells)
    placements = pack_staples_then_merge(cells, staples, color)
    best_sec = check_connectivity(placements_to_bricks(placements)).section_count
    best_cells = set(cells)
    best_placements = list(placements)
    print(f"  reinforce start sections={best_sec}")

    for rnd in range(max_rounds):
        report = check_connectivity(placements_to_bricks(placements))
        sec = report.section_count
        print(f"  reinforce round {rnd}: sections={sec} voxels={len(cells)}")
        if sec < best_sec:
            best_sec = sec
            best_cells = set(cells)
            best_placements = list(placements)
        if sec <= 1:
            break

        main_ids = set(report.components[report.largest_component_id])
        main_vox: set[tuple[int, int, int]] = set()
        island_vox: set[tuple[int, int, int]] = set()
        for i, p in enumerate(placements):
            pcs = _placement_cells(p)
            if i in main_ids:
                main_vox |= pcs
            else:
                island_vox |= pcs

        # Staples only at contacts — do NOT flood-fill paths (that packed red)
        forced = _contact_clutch_staples(island_vox, main_vox, solid_set, cells)
        if not forced:
            break

        # Tiny vertical bridge cells only (cap)
        for iy_a, ca, cb in forced:
            for col in (ca, cb):
                for dy in (-1, 0, 1):
                    c = (col[0], iy_a + dy, col[1])
                    if c in solid_set and len(cells) < budget:
                        cells.add(c)

        staples = forced + choose_column_staples(cells)
        placements = pack_staples_then_merge(cells, staples, color)
        new_sec = check_connectivity(placements_to_bricks(placements)).section_count
        if new_sec < best_sec:
            best_sec = new_sec
            best_cells = set(cells)
            best_placements = list(placements)
        else:
            cells = set(best_cells)
            placements = list(best_placements)
            break

    cells = set(best_cells)
    placements = list(best_placements)
    staples = choose_column_staples(cells)
    merged = pack_staples_then_merge(cells, staples, color)
    sec = check_connectivity(placements_to_bricks(merged)).section_count
    if sec <= best_sec:
        placements = merged
        best_sec = sec
    else:
        placements = best_placements
        sec = best_sec

    print(
        f"  reinforce final: sections={sec} "
        f"voxels={len(cells)} ({100 * len(cells) / len(solid_set):.0f}%) "
        f"parts={len(placements)}"
    )
    return cells, placements, sec, shell_set


def pin_columns_for_set(
    keep: set[tuple[int, int, int]],
    solid_set: set[tuple[int, int, int]],
) -> set[tuple[int, int, int]]:
    cols = {(ix, iz) for ix, _iy, iz in keep}
    out = set(keep)
    for ix, iy, iz in solid_set:
        if (ix, iz) in cols:
            out.add((ix, iy, iz))
    return out


def build_hollow_structure(
    solid: list[Voxel],
    *,
    color: int = 14,
    stride: int = 2,
    floor_every: int = 2,
    belt_every: int = 2,
    pin_columns: bool = False,
) -> StructureReport:
    """
    Hollow shell + sparse in-solid lattice, then tie clutch islands through
    the solid and merge into large bricks.
    """
    from scaffold import shell_plus_scaffold  # noqa: WPS433

    original = _as_set(solid)
    _shell, _interior, _scaffold, combined = shell_plus_scaffold(
        solid,
        stride=stride,
        floor_every=floor_every,
        belt_every=belt_every,
        pin_columns=pin_columns,
    )
    cells = _as_set(combined)
    cells, placements, sections = tie_islands_through_solid(
        cells, original, color
    )

    return StructureReport(
        placements=placements,
        voxels=_to_voxels(cells),
        section_count=sections,
        voxels_added=len(cells) - len(original),
        dilate_used=0,
        six_cc=count_6(cells),
    )
