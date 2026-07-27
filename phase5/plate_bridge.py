"""
Phase 5 — Smooth exterior + studded underside / cavity strips + min staples.

- Exterior tops only: smooth TILES facing outside air.
- Cavity-facing tops stay studded; studded PLATES join sections there.
- Underside plates for cantilevers / ears.
- Minimum solid-only vertical 1x1 staples to create cross-layer clutch.
- All placements AABB-collision-checked.
"""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase4"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import BRICK_H, PLATE_H, STUD, packing_templates  # noqa: E402
from export_io import Brick  # noqa: E402
from greedy import IDENTITY, Placement, placements_to_bricks  # noqa: E402
from connectivity import check_connectivity  # noqa: E402
from brick_collision import CollisionWorld, collides_any, count_collisions  # noqa: E402


@dataclass(frozen=True)
class StripTemplate:
    part_id: str
    w: int
    d: int
    rot: tuple[float, ...]

    @property
    def world_w(self) -> int:
        return self.d if self.rot != IDENTITY else self.w

    @property
    def world_d(self) -> int:
        return self.w if self.rot != IDENTITY else self.d


def _strip_templates(kind: str) -> list[StripTemplate]:
    return [
        StripTemplate(t.part_id, t.w, t.d, t.rot) for t in packing_templates(kind)
    ]


TILE_TEMPLATES: list[StripTemplate] = _strip_templates("tile")
PLATE_TEMPLATES: list[StripTemplate] = _strip_templates("plate")

SolidCells = set[tuple[int, int, int]]


def _brick_top_y(iy: int) -> float:
    return -float((iy + 1) * BRICK_H)


def _brick_bottom_y(iy: int) -> float:
    return -float(iy * BRICK_H)


def _make_part(
    part_id: str,
    color: int,
    ix: int,
    iz: int,
    w: int,
    d: int,
    rot: tuple[float, ...],
    origin_y: float,
) -> Brick:
    sx = ix + w / 2.0
    sz = iz + d / 2.0
    a, b, c, d_, e, f, g, h, i = rot
    return Brick(
        part_id=part_id,
        color=color,
        x=sx * STUD,
        y=origin_y,
        z=sz * STUD,
        a=a, b=b, c=c, d=d_, e=e, f=f, g=g, h=h, i=i,
    )


def _make_1x1_brick(color: int, ix: int, iy: int, iz: int) -> Brick:
    return _make_part("3005.dat", color, ix, iz, 1, 1, IDENTITY, _brick_top_y(iy))


def _1x1_brick_voxel(b: Brick) -> tuple[int, int, int] | None:
    if b.part_id != "3005.dat":
        return None
    ix = int(round(b.x / STUD - 0.5))
    iz = int(round(b.z / STUD - 0.5))
    iy = int(round(-b.y / BRICK_H - 1.0))
    return (ix, iy, iz)


def _footprint_cells(p: Placement) -> set[tuple[int, int]]:
    return {
        (x, z)
        for x in range(p.ix, p.ix + p.w)
        for z in range(p.iz, p.iz + p.d)
    }


def _placement_voxels(placements: list[Placement]) -> set[tuple[int, int, int]]:
    out: set[tuple[int, int, int]] = set()
    for p in placements:
        for x, z in _footprint_cells(p):
            out.add((x, p.iy, z))
    return out


def _occupancy_by_layer(placements: list[Placement]) -> dict[int, set[tuple[int, int]]]:
    layers: dict[int, set[tuple[int, int]]] = {}
    for p in placements:
        layers.setdefault(p.iy, set()).update(_footprint_cells(p))
    return layers


def _layer_section_map(
    placements: list[Placement],
    component_of: list[int],
) -> dict[int, dict[tuple[int, int], int]]:
    layers: dict[int, dict[tuple[int, int], int]] = {}
    for i, p in enumerate(placements):
        sec = component_of[i]
        layer = layers.setdefault(p.iy, {})
        for cell in _footprint_cells(p):
            layer[cell] = sec
    return layers


def _all_cells_present(
    need: set[tuple[int, int]],
    have: set[tuple[int, int]] | dict[tuple[int, int], int],
) -> bool:
    return need <= set(have)


def _top_faces_outside(
    ix: int,
    iy: int,
    iz: int,
    solid: SolidCells | None,
) -> bool:
    if solid is None:
        return True
    return (ix, iy + 1, iz) not in solid


def exterior_exposed_cells(
    placements: list[Placement],
    solid: SolidCells | None = None,
) -> dict[int, set[tuple[int, int]]]:
    occ = _occupancy_by_layer(placements)
    out: dict[int, set[tuple[int, int]]] = {}
    for iy, cells in occ.items():
        above = occ.get(iy + 1, set())
        exposed = {
            (x, z)
            for x, z in cells
            if (x, z) not in above and _top_faces_outside(x, iy, z, solid)
        }
        if exposed:
            out[iy] = exposed
    return out


def cavity_facing_cells(
    placements: list[Placement],
    solid: SolidCells,
) -> dict[int, set[tuple[int, int]]]:
    occ = _occupancy_by_layer(placements)
    out: dict[int, set[tuple[int, int]]] = {}
    for iy, cells in occ.items():
        above = occ.get(iy + 1, set())
        cavity = {
            (x, z)
            for x, z in cells
            if (x, z) not in above and (x, iy + 1, z) in solid
        }
        if cavity:
            out[iy] = cavity
    return out


def cover_exterior_with_tiles(
    placements: list[Placement],
    existing: list[Brick],
    *,
    tile_color: int = 15,
    solid: SolidCells | None = None,
) -> tuple[list[Brick], int]:
    to_cover = exterior_exposed_cells(placements, solid)
    tiles: list[Brick] = []
    covered: dict[int, set[tuple[int, int]]] = {}
    index = CollisionWorld(existing)

    def try_tile(
        part_id: str,
        ix: int,
        iz: int,
        ww: int,
        dd: int,
        rot: tuple[float, ...],
        iy: int,
    ) -> Brick | None:
        # Prefer flush on brick; if a plate already sits there, stack on the plate.
        for origin_y in (
            _brick_top_y(iy) - PLATE_H,
            _brick_top_y(iy) - 2 * PLATE_H,
        ):
            cand = _make_part(part_id, tile_color, ix, iz, ww, dd, rot, origin_y)
            if not index.collides(cand):
                return cand
        return None

    for iy in sorted(to_cover):
        exposed = to_cover[iy]
        used = covered.setdefault(iy, set())
        remaining = set(exposed)
        ixs = [x for x, _z in exposed]
        izs = [z for _x, z in exposed]
        x0, x1 = min(ixs), max(ixs)
        z0, z1 = min(izs), max(izs)

        for tmpl in TILE_TEMPLATES:
            ww, dd = tmpl.world_w, tmpl.world_d
            for ix in range(x0, x1 - ww + 2):
                for iz in range(z0, z1 - dd + 2):
                    cells = {
                        (x, z)
                        for x in range(ix, ix + ww)
                        for z in range(iz, iz + dd)
                    }
                    if not cells <= remaining or cells & used:
                        continue
                    cand = try_tile(tmpl.part_id, ix, iz, ww, dd, tmpl.rot, iy)
                    if cand is None:
                        continue
                    tiles.append(cand)
                    index.add(cand)
                    used |= cells
                    remaining -= cells

        for ix, iz in sorted(remaining):
            cand = try_tile("3070b.dat", ix, iz, 1, 1, IDENTITY, iy)
            if cand is None:
                continue
            tiles.append(cand)
            index.add(cand)
            used.add((ix, iz))
            remaining.discard((ix, iz))

        covered[iy] = used

    uncovered = sum(
        len(exposed - covered.get(iy, set())) for iy, exposed in to_cover.items()
    )
    return tiles, uncovered


def _plate_bridge_round(
    *,
    free_by_layer: dict[int, dict[tuple[int, int], int]],
    used: dict[int, set[tuple[int, int]]],
    world: list[Brick],
    index: CollisionWorld,
    origin_y_fn,
    plate_color: int,
    require_multi_section: bool = True,
) -> tuple[list[Brick], int]:
    plates: list[Brick] = []
    placed = 0
    for iy, free in sorted(free_by_layer.items()):
        if not free:
            continue
        layer_used = used.setdefault(iy, set())
        ixs = [x for x, _z in free]
        izs = [z for _x, z in free]
        x0, x1 = min(ixs), max(ixs)
        z0, z1 = min(izs), max(izs)
        origin_y = origin_y_fn(iy)

        for tmpl in PLATE_TEMPLATES:
            ww, dd = tmpl.world_w, tmpl.world_d
            for ix in range(x0, x1 - ww + 2):
                for iz in range(z0, z1 - dd + 2):
                    cells = {
                        (x, z)
                        for x in range(ix, ix + ww)
                        for z in range(iz, iz + dd)
                    }
                    if not _all_cells_present(cells, free):
                        continue
                    if cells & layer_used:
                        continue
                    if require_multi_section and len({free[c] for c in cells}) < 2:
                        continue
                    cand = _make_part(
                        tmpl.part_id, plate_color, ix, iz, ww, dd, tmpl.rot, origin_y
                    )
                    if index.collides(cand):
                        continue
                    plates.append(cand)
                    world.append(cand)
                    index.add(cand)
                    layer_used |= cells
                    placed += 1
    return plates, placed


def bridge_under_with_plates(
    placements: list[Placement],
    existing: list[Brick],
    *,
    plate_color: int = 72,
    max_rounds: int = 40,
) -> tuple[list[Brick], int, int]:
    shell = placements_to_bricks(placements)
    before = check_connectivity(shell + existing).section_count
    plates: list[Brick] = []
    used_under: dict[int, set[tuple[int, int]]] = {}
    world = list(shell) + list(existing)
    index = CollisionWorld(world)

    for rnd in range(max_rounds):
        report = check_connectivity(world)
        if report.section_count <= 1:
            break
        component_of = report.component_of[: len(shell)]
        layers = _layer_section_map(placements, component_of)
        occ = {iy: set(m) for iy, m in layers.items()}

        free_by_layer: dict[int, dict[tuple[int, int], int]] = {}
        for iy, layer in layers.items():
            below = occ.get(iy - 1, set())
            free = {c: s for c, s in layer.items() if c not in below}
            if free:
                free_by_layer[iy] = free

        new_plates, placed = _plate_bridge_round(
            free_by_layer=free_by_layer,
            used=used_under,
            world=world,
            index=index,
            origin_y_fn=_brick_bottom_y,
            plate_color=plate_color,
        )
        plates.extend(new_plates)
        if placed == 0:
            break
        new_sec = check_connectivity(world).section_count
        print(f"    under-plate round {rnd}: +{placed} -> {new_sec} sections")
        if new_sec >= report.section_count:
            break

    return plates, before, check_connectivity(world).section_count


def _collect_staple_vox(
    placements: list[Placement],
    existing: list[Brick],
    prior: set[tuple[int, int, int]],
) -> set[tuple[int, int, int]]:
    shell_vox = _placement_voxels(placements)
    out = set(prior)
    for b in existing:
        cell = _1x1_brick_voxel(b)
        if cell is not None and cell not in shell_vox:
            out.add(cell)
    return out


def _section_layers_with_staples(
    placements: list[Placement],
    staple_vox: set[tuple[int, int, int]],
    world: list[Brick],
) -> dict[int, dict[tuple[int, int], int]]:
    report = check_connectivity(world)
    layers: dict[int, dict[tuple[int, int], int]] = {}
    for i, p in enumerate(placements):
        sec = report.component_of[i]
        layer = layers.setdefault(p.iy, {})
        for cell in _footprint_cells(p):
            layer[cell] = sec
    for i, b in enumerate(world):
        cell = _1x1_brick_voxel(b)
        if cell is None or cell not in staple_vox:
            continue
        ix, iy, iz = cell
        layers.setdefault(iy, {})[(ix, iz)] = report.component_of[i]
    return layers


def bridge_tops_with_plates(
    placements: list[Placement],
    existing: list[Brick],
    *,
    plate_color: int = 72,
    max_rounds: int = 40,
    staple_vox: set[tuple[int, int, int]] | None = None,
) -> tuple[list[Brick], int, int]:
    """
    Studded plates on ANY top with no brick above, spanning ≥2 sections.

    First places explicit 1x2 contact plates on every edge-adjacent pair of
    different sections, then falls back to catalog packing for larger spans.
    """
    shell = placements_to_bricks(placements)
    before = check_connectivity(shell + existing).section_count
    plates: list[Brick] = []
    used_top: dict[int, set[tuple[int, int]]] = {}
    world = list(shell) + list(existing)
    index = CollisionWorld(world)
    staples = _collect_staple_vox(placements, existing, staple_vox or set())
    occ = _occupancy_by_layer(placements)
    yaw90 = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)

    exposed: dict[int, set[tuple[int, int]]] = {}
    for iy, cells in occ.items():
        above = occ.get(iy + 1, set()) | {
            (x, z) for x, y, z in staples if y == iy + 1
        }
        free = {(x, z) for x, z in cells if (x, z) not in above}
        if free:
            exposed.setdefault(iy, set()).update(free)
    for ix, iy, iz in staples:
        above_shell = occ.get(iy + 1, set())
        if (ix, iz) in above_shell or (ix, iy + 1, iz) in staples:
            continue
        exposed.setdefault(iy, set()).add((ix, iz))

    for rnd in range(max_rounds):
        report = check_connectivity(world)
        if report.section_count <= 1:
            break
        sec_before = report.section_count
        layers = _section_layers_with_staples(placements, staples, world)
        placed = 0

        # Explicit 1x2 contacts on adjacent different-section cells
        for iy, cells in sorted(exposed.items()):
            layer = layers.get(iy, {})
            layer_used = used_top.setdefault(iy, set())
            for ix, iz in sorted(cells):
                if (ix, iz) not in layer or (ix, iz) in layer_used:
                    continue
                sec = layer[(ix, iz)]
                for dx, dz, pw, pd, rot in (
                    (1, 0, 2, 1, IDENTITY),
                    (0, 1, 1, 2, yaw90),
                ):
                    n = (ix + dx, iz + dz)
                    if n not in cells or n not in layer or n in layer_used:
                        continue
                    if layer[n] == sec:
                        continue
                    px, pz = min(ix, n[0]), min(iz, n[1])
                    plate = _make_part(
                        "3023.dat",
                        plate_color,
                        px,
                        pz,
                        pw,
                        pd,
                        rot,
                        _brick_top_y(iy) - PLATE_H,
                    )
                    if index.collides(plate):
                        continue
                    world.append(plate)
                    index.add(plate)
                    plates.append(plate)
                    layer_used.add((ix, iz))
                    layer_used.add(n)
                    placed += 1
                    break

        if placed == 0:
            # Larger multi-section strips on remaining free tops
            free_by_layer: dict[int, dict[tuple[int, int], int]] = {}
            for iy, cells in exposed.items():
                layer = layers.get(iy, {})
                layer_used = used_top.setdefault(iy, set())
                free = {
                    c: layer[c]
                    for c in cells
                    if c in layer and c not in layer_used
                }
                if free:
                    free_by_layer[iy] = free
            more, n = _plate_bridge_round(
                free_by_layer=free_by_layer,
                used=used_top,
                world=world,
                index=index,
                origin_y_fn=lambda iy: _brick_top_y(iy) - PLATE_H,
                plate_color=plate_color,
                require_multi_section=True,
            )
            plates.extend(more)
            placed = n

        if placed == 0:
            break
        new_sec = check_connectivity(world).section_count
        print(f"    top-plate round {rnd}: +{placed} -> {new_sec} sections")
        if new_sec >= sec_before:
            break

    return plates, before, check_connectivity(world).section_count


def bridge_cavity_with_plates(
    placements: list[Placement],
    existing: list[Brick],
    solid: SolidCells,
    *,
    plate_color: int = 72,
    max_rounds: int = 40,
    staple_vox: set[tuple[int, int, int]] | None = None,
) -> tuple[list[Brick], int, int]:
    """Alias: plate-bridge all open tops (cavity + exterior nubs)."""
    del solid
    return bridge_tops_with_plates(
        placements,
        existing,
        plate_color=plate_color,
        max_rounds=max_rounds,
        staple_vox=staple_vox,
    )


def staple_vertical_gaps(
    placements: list[Placement],
    existing: list[Brick],
    solid: SolidCells,
    *,
    staple_color: int = 71,
    plate_color: int = 72,
    max_rounds: int = 400,
    max_gap: int = 3,
    prior_staple_vox: set[tuple[int, int, int]] | None = None,
) -> tuple[list[Brick], set[tuple[int, int, int]], int, int]:
    """
    Minimum solid-only repairs that reduce clutch sections:

    1) Fill short same-column gaps (≤ max_gap) with 1x1 bricks.
    2) Batch stair joins: 1x1 nub + 1x2 plate to a neighbor section above.
    """
    shell = placements_to_bricks(placements)
    before = check_connectivity(shell + existing).section_count
    new_parts: list[Brick] = []
    occupied = _placement_voxels(placements)
    staple_vox = _collect_staple_vox(placements, existing, prior_staple_vox or set())
    world = list(shell) + list(existing)
    index = CollisionWorld(world)
    yaw90 = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)

    def free_solid() -> set[tuple[int, int, int]]:
        return solid - occupied - staple_vox

    def voxel_sections() -> dict[tuple[int, int, int], int]:
        report = check_connectivity(world)
        out: dict[tuple[int, int, int], int] = {}
        for i, p in enumerate(placements):
            for x, z in _footprint_cells(p):
                out[(x, p.iy, z)] = report.component_of[i]
        for i, b in enumerate(world):
            cell = _1x1_brick_voxel(b)
            if cell is not None and cell in staple_vox:
                out[cell] = report.component_of[i]
        return out

    for _rnd in range(max_rounds):
        report = check_connectivity(world)
        if report.section_count <= 1:
            break
        sec_before = report.section_count
        vsec = voxel_sections()

        by_col: dict[tuple[int, int], list[int]] = {}
        for ix, iy, iz in occupied | staple_vox:
            by_col.setdefault((ix, iz), []).append(iy)
        for col in by_col:
            by_col[col].sort()

        made_progress = False

        # (1) Batch short vertical gap fills
        gap_cells: list[tuple[int, int, int]] = []
        seen_gap: set[tuple[int, int, int]] = set()
        for (ix, iz), heights in by_col.items():
            for a, b in zip(heights, heights[1:]):
                gap = b - a - 1
                if gap < 1 or gap > max_gap:
                    continue
                sa, sb = vsec.get((ix, a, iz)), vsec.get((ix, b, iz))
                if sa is None or sb is None or sa == sb:
                    continue
                for iy in range(a + 1, b):
                    cell = (ix, iy, iz)
                    if cell in free_solid() and cell not in seen_gap:
                        gap_cells.append(cell)
                        seen_gap.add(cell)
        if gap_cells:
            snap_w, snap_p, snap_v = len(world), len(new_parts), set(staple_vox)
            n_added = 0
            for cell in gap_cells:
                if cell not in free_solid():
                    continue
                ix, iy, iz = cell
                cand = _make_1x1_brick(staple_color, ix, iy, iz)
                if index.collides(cand):
                    continue
                world.append(cand)
                index.add(cand)
                staple_vox.add(cell)
                new_parts.append(cand)
                n_added += 1
            new_sec = check_connectivity(world).section_count
            if n_added and new_sec < sec_before:
                print(f"    staple gaps +{n_added} -> {new_sec} sections")
                made_progress = True
                continue
            while len(world) > snap_w:
                world.pop()
            del new_parts[snap_p:]
            staple_vox.clear()
            staple_vox.update(snap_v)
            index = CollisionWorld(world)

        # (2) Batch stair joins — collision-checked nub + plate
        used_nubs: set[tuple[int, int, int]] = set()
        used_plate_cells: set[tuple[int, int]] = set()
        batch: list[Brick] = []
        batch_nubs: list[tuple[int, int, int]] = []
        trial = CollisionWorld(world)

        for (ix, iy, iz), sec in vsec.items():
            if (ix, iy, iz) not in occupied and (ix, iy, iz) not in staple_vox:
                continue
            nub = (ix, iy + 1, iz)
            if nub not in free_solid() or nub in used_nubs:
                continue
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (ix + dx, iy + 1, iz + dz)
                if n not in vsec or vsec[n] == sec:
                    continue
                nx, _ny, nz = n
                if iz == nz:
                    px, pz, pw, pd, rot = min(ix, nx), iz, 2, 1, IDENTITY
                elif ix == nx:
                    px, pz, pw, pd, rot = ix, min(iz, nz), 1, 2, yaw90
                else:
                    continue
                plate_cells = {
                    (x, z)
                    for x in range(px, px + pw)
                    for z in range(pz, pz + pd)
                }
                if plate_cells & used_plate_cells:
                    continue
                nub_brick = _make_1x1_brick(staple_color, ix, iy + 1, iz)
                plate = _make_part(
                    "3023.dat",
                    plate_color,
                    px,
                    pz,
                    pw,
                    pd,
                    rot,
                    _brick_top_y(iy + 1) - PLATE_H,
                )
                if trial.collides(nub_brick) or trial.collides(plate):
                    continue
                trial.add(nub_brick)
                trial.add(plate)
                batch.extend([nub_brick, plate])
                batch_nubs.append(nub)
                used_nubs.add(nub)
                used_plate_cells |= plate_cells
                break

        if batch:
            snap_w = len(world)
            world.extend(batch)
            for nub in batch_nubs:
                staple_vox.add(nub)
            new_sec = check_connectivity(world).section_count
            if new_sec < sec_before:
                new_parts.extend(batch)
                index = trial
                print(
                    f"    staple stairs +{len(batch_nubs)} -> {new_sec} sections"
                )
                made_progress = True
                continue
            del world[snap_w:]
            for nub in batch_nubs:
                staple_vox.discard(nub)
            index = CollisionWorld(world)

        if made_progress:
            continue

        # (3) Minimal column spines: shortest gaps that unite different sections
        free = free_solid()
        parent: dict[int, int] = {}

        def find(s: int) -> int:
            parent.setdefault(s, s)
            while parent[s] != s:
                parent[s] = parent[parent[s]]
                s = parent[s]
            return s

        def union(a: int, b: int) -> bool:
            ra, rb = find(a), find(b)
            if ra == rb:
                return False
            parent[rb] = ra
            return True

        for sec in {s for s in vsec.values()}:
            parent[sec] = sec

        candidates: list[tuple[int, int, int, int, int, int, int]] = []
        for (ix, iz), heights in by_col.items():
            for a, b in zip(heights, heights[1:]):
                gap = b - a - 1
                if gap < 1:
                    continue
                sa, sb = vsec.get((ix, a, iz)), vsec.get((ix, b, iz))
                if sa is None or sb is None or sa == sb:
                    continue
                candidates.append((gap, ix, iz, a, b, sa, sb))
        candidates.sort()

        spine_cells: list[tuple[int, int, int]] = []
        for gap, ix, iz, a, b, sa, sb in candidates:
            if find(sa) == find(sb):
                continue
            cells = [(ix, iy, iz) for iy in range(a + 1, b)]
            if not cells or any(c not in free for c in cells):
                continue
            if not union(sa, sb):
                continue
            spine_cells.extend(cells)
            for c in cells:
                free.discard(c)
            if len({find(s) for s in parent}) <= 1:
                break

        if spine_cells:
            snap_w, snap_p, snap_v = len(world), len(new_parts), set(staple_vox)
            ok = True
            for cell in spine_cells:
                ix, iy_fill, iz = cell
                brick = _make_1x1_brick(staple_color, ix, iy_fill, iz)
                if index.collides(brick):
                    ok = False
                    break
                world.append(brick)
                index.add(brick)
                new_parts.append(brick)
                staple_vox.add(cell)
            if ok:
                after = check_connectivity(world).section_count
                if after < sec_before:
                    print(
                        f"    column spines +{len(spine_cells)} -> {after} sections"
                    )
                    made_progress = True
                    continue
            while len(world) > snap_w:
                world.pop()
            del new_parts[snap_p:]
            staple_vox.clear()
            staple_vox.update(snap_v)
            index = CollisionWorld(world)

        break

    return new_parts, staple_vox, before, check_connectivity(world).section_count


def _plate_1x2_on_pair(
    c0: tuple[int, int, int],
    c1: tuple[int, int, int],
    plate_color: int,
) -> Brick | None:
    """1x2 plate on two same-layer orthogonally adjacent cells, or None."""
    if c0[1] != c1[1]:
        return None
    yaw90 = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)
    if c0[2] == c1[2] and abs(c0[0] - c1[0]) == 1:
        return _make_part(
            "3023.dat",
            plate_color,
            min(c0[0], c1[0]),
            c0[2],
            2,
            1,
            IDENTITY,
            _brick_top_y(c0[1]) - PLATE_H,
        )
    if c0[0] == c1[0] and abs(c0[2] - c1[2]) == 1:
        return _make_part(
            "3023.dat",
            plate_color,
            c0[0],
            min(c0[2], c1[2]),
            1,
            2,
            yaw90,
            _brick_top_y(c0[1]) - PLATE_H,
        )
    return None


def _span_plate_on_pair(
    c0: tuple[int, int, int],
    c1: tuple[int, int, int],
    plate_color: int,
) -> Brick | None:
    """Axis-aligned plate spanning two same-layer cells (gap up to 3 studs)."""
    if c0[1] != c1[1]:
        return None
    yaw90 = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)
    y = c0[1]
    top = _brick_top_y(y) - PLATE_H
    # Same Z row → plate along X
    if c0[2] == c1[2]:
        x0, x1 = sorted((c0[0], c1[0]))
        span = x1 - x0 + 1
        if span < 2 or span > 4:
            return None
        part = {2: "3023.dat", 3: "3623.dat", 4: "3710.dat"}[span]
        return _make_part(part, plate_color, x0, c0[2], span, 1, IDENTITY, top)
    # Same X column → plate along Z
    if c0[0] == c1[0]:
        z0, z1 = sorted((c0[2], c1[2]))
        span = z1 - z0 + 1
        if span < 2 or span > 4:
            return None
        part = {2: "3023.dat", 3: "3623.dat", 4: "3710.dat"}[span]
        return _make_part(part, plate_color, c0[0], z0, 1, span, yaw90, top)
    return None


def _bridge_air_gaps_with_plates(
    placements: list[Placement],
    existing: list[Brick],
    *,
    plate_color: int,
    staple_vox: set[tuple[int, int, int]],
    max_span: int = 4,
) -> list[Brick]:
    """Join different sections with plates that may span empty air between studs."""
    shell = placements_to_bricks(placements)
    world = list(shell) + list(existing)
    before = check_connectivity(world).section_count
    if before <= 1:
        return []

    report = check_connectivity(world)
    vsec: dict[tuple[int, int, int], int] = {}
    for i, p in enumerate(placements):
        for x, z in _footprint_cells(p):
            vsec[(x, p.iy, z)] = report.component_of[i]
    for i, b in enumerate(world):
        cell = _1x1_brick_voxel(b)
        if cell is not None and cell in staple_vox:
            vsec[cell] = report.component_of[i]

    by_layer: dict[int, dict[tuple[int, int], int]] = {}
    for (x, y, z), sec in vsec.items():
        by_layer.setdefault(y, {})[(x, z)] = sec

    added: list[Brick] = []
    used: dict[int, set[tuple[int, int]]] = {}

    for y, cells in sorted(by_layer.items()):
        layer_used = used.setdefault(y, set())
        items = list(cells.items())
        # Prefer short spans
        for span in range(2, max_span + 1):
            made = True
            while made:
                made = False
                report = check_connectivity(world)
                if report.section_count <= 1:
                    return added
                # refresh sections cheaply from current component map of bricks
                # (cell→sec may be stale after merges; rebuild from vsec labels via union)
                cur_sec = {}
                for i, p in enumerate(placements):
                    for x, z in _footprint_cells(p):
                        cur_sec[(x, p.iy, z)] = report.component_of[i]
                for i, b in enumerate(world):
                    cell = _1x1_brick_voxel(b)
                    if cell is not None and cell in staple_vox:
                        cur_sec[cell] = report.component_of[i]
                for (x, z), _old in items:
                    if (x, y, z) not in cur_sec:
                        continue
                    if (x, z) in layer_used:
                        continue
                    sec = cur_sec[(x, y, z)]
                    for dx, dz in ((span - 1, 0), (0, span - 1)):
                        n = (x + dx, z + dz)
                        if n not in cells or n in layer_used:
                            continue
                        nb = (x + dx, y, z + dz)
                        if nb not in cur_sec or cur_sec[nb] == sec:
                            continue
                        plate = _span_plate_on_pair(
                            (x, y, z), nb, plate_color
                        )
                        if plate is None or collides_any(plate, world):
                            continue
                        world.append(plate)
                        new_sec = check_connectivity(world).section_count
                        if new_sec < before:
                            added.append(plate)
                            layer_used.add((x, z))
                            layer_used.add(n)
                            before = new_sec
                            print(
                                f"    air-span plate {span} -> {new_sec} sections"
                            )
                            made = True
                            break
                        world.pop()
                    if made:
                        break
    return added


def _staple_air_column_gaps(
    placements: list[Placement],
    existing: list[Brick],
    *,
    staple_color: int,
    staple_vox: set[tuple[int, int, int]],
    max_gap: int = 6,
) -> list[Brick]:
    """Last resort: fill short same-column air gaps between different sections."""
    shell = placements_to_bricks(placements)
    world = list(shell) + list(existing)
    before = check_connectivity(world).section_count
    if before <= 1:
        return []

    report = check_connectivity(world)
    vsec: dict[tuple[int, int, int], int] = {}
    for i, p in enumerate(placements):
        for x, z in _footprint_cells(p):
            vsec[(x, p.iy, z)] = report.component_of[i]
    for i, b in enumerate(world):
        cell = _1x1_brick_voxel(b)
        if cell is not None and cell in staple_vox:
            vsec[cell] = report.component_of[i]

    by_col: dict[tuple[int, int], list[int]] = {}
    for x, y, z in vsec:
        by_col.setdefault((x, z), []).append(y)
    for col in by_col:
        by_col[col].sort()

    parent: dict[int, int] = {s: s for s in set(vsec.values())}

    def find(s: int) -> int:
        while parent[s] != s:
            parent[s] = parent[parent[s]]
            s = parent[s]
        return s

    def union(a: int, b: int) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[rb] = ra
        return True

    candidates: list[tuple[int, int, int, int, int, int, int]] = []
    occupied = set(vsec) | set(staple_vox)
    for (ix, iz), heights in by_col.items():
        for a, b in zip(heights, heights[1:]):
            gap = b - a - 1
            if gap < 1 or gap > max_gap:
                continue
            sa, sb = vsec[(ix, a, iz)], vsec[(ix, b, iz)]
            if sa == sb:
                continue
            mids = [(ix, iy, iz) for iy in range(a + 1, b)]
            if any(c in occupied for c in mids):
                continue
            candidates.append((gap, ix, iz, a, b, sa, sb))
    candidates.sort()

    added: list[Brick] = []
    for gap, ix, iz, a, b, sa, sb in candidates:
        if find(sa) == find(sb):
            continue
        snap_w, snap_a = len(world), len(added)
        snap_v = set(staple_vox)
        for iy in range(a + 1, b):
            cell = (ix, iy, iz)
            brick = _make_1x1_brick(staple_color, ix, iy, iz)
            world.append(brick)
            added.append(brick)
            staple_vox.add(cell)
        after = check_connectivity(world).section_count
        if after < before:
            union(sa, sb)
            print(f"    air-column +{gap} -> {after} sections")
            before = after
            if before <= 1:
                break
            continue
        while len(world) > snap_w:
            world.pop()
        del added[snap_a:]
        staple_vox.clear()
        staple_vox.update(snap_v)
    return added


def _staple_nearest_air_path(
    placements: list[Placement],
    existing: list[Brick],
    *,
    staple_color: int,
    plate_color: int,
    staple_vox: set[tuple[int, int, int]],
    max_dist: int = 16,
) -> list[Brick]:
    """Connect the smallest section to the largest via a short air L-path of 1x1s."""
    shell = placements_to_bricks(placements)
    world = list(shell) + list(existing)
    before = check_connectivity(world).section_count
    if before <= 1:
        return []

    report = check_connectivity(world)
    vsec: dict[tuple[int, int, int], int] = {}
    for i, p in enumerate(placements):
        for x, z in _footprint_cells(p):
            vsec[(x, p.iy, z)] = report.component_of[i]
    for i, b in enumerate(world):
        cell = _1x1_brick_voxel(b)
        if cell is not None and cell in staple_vox:
            vsec[cell] = report.component_of[i]

    by_sec: dict[int, list[tuple[int, int, int]]] = {}
    for cell, sec in vsec.items():
        by_sec.setdefault(sec, []).append(cell)
    if len(by_sec) < 2:
        return []
    largest = max(by_sec, key=lambda s: len(by_sec[s]))
    small = min((s for s in by_sec if s != largest), key=lambda s: len(by_sec[s]))
    members = by_sec[small]
    goals = by_sec[largest]
    occupied = set(vsec) | set(staple_vox)

    best = None
    best_d = 10**9
    for a in members:
        for b in goals:
            d = abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
            if d < best_d:
                best_d = d
                best = (a, b)
    if best is None or best_d < 2 or best_d > max_dist:
        return []
    a, b = best

    def try_path(order: str) -> list[tuple[int, int, int]]:
        fill: list[tuple[int, int, int]] = []
        x, y, z = a
        for axis in order:
            target = b[{"x": 0, "y": 1, "z": 2}[axis]]
            while {"x": x, "y": y, "z": z}[axis] != target:
                if axis == "x":
                    x += 1 if b[0] > x else -1
                elif axis == "y":
                    y += 1 if b[1] > y else -1
                else:
                    z += 1 if b[2] > z else -1
                cell = (x, y, z)
                if cell == b:
                    return fill
                if cell in occupied:
                    return []
                fill.append(cell)
        return fill

    fill = try_path("yxz") or try_path("xyz") or try_path("xzy")
    if not fill:
        return []

    snap = len(world)
    added: list[Brick] = []
    for fx, fy, fz in fill:
        brick = _make_1x1_brick(staple_color, fx, fy, fz)
        world.append(brick)
        added.append(brick)
        staple_vox.add((fx, fy, fz))
    chain = [a] + fill + [b]
    for i in range(len(chain) - 1):
        plate = _plate_1x2_on_pair(chain[i], chain[i + 1], plate_color)
        if plate is not None:
            world.append(plate)
            added.append(plate)
    after = check_connectivity(world).section_count
    if after < before:
        print(f"    nearest-air path +{len(fill)} -> {after} sections")
        return added
    while len(world) > snap:
        world.pop()
    for fx, fy, fz in fill:
        staple_vox.discard((fx, fy, fz))
    return []


def _bfs_fill_path(
    starts: list[tuple[int, int, int]],
    goals: list[tuple[int, int, int]],
    free: set[tuple[int, int, int]],
    *,
    max_dist: int = 48,
    max_visit: int = 12000,
) -> tuple[list[tuple[int, int, int]], tuple[int, int, int] | None, tuple[int, int, int] | None]:
    """Shortest path through free solid from a start-neighbor to a goal-neighbor.

    Returns (fill_cells, start_endpoint, goal_endpoint). Endpoints are existing
    component voxels used for plate/clutch attachment; fill excludes them.
    """
    goal_set = set(goals)
    start_set = set(starts)
    q: deque[tuple[tuple[int, int, int], int]] = deque()
    parent: dict[tuple[int, int, int], tuple[int, int, int] | None] = {}
    attach_start: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    neigh = (
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (0, 0, 1),
        (0, 0, -1),
    )

    for sx, sy, sz in starts:
        for dx, dy, dz in neigh:
            n = (sx + dx, sy + dy, sz + dz)
            if n in free and n not in parent:
                parent[n] = None
                attach_start[n] = (sx, sy, sz)
                q.append((n, 1))

    while q:
        cur, dist = q.popleft()
        cx, cy, cz = cur
        for dx, dy, dz in neigh:
            nb = (cx + dx, cy + dy, cz + dz)
            if nb in goal_set:
                path = [cur]
                p = parent[cur]
                while p is not None:
                    path.append(p)
                    p = parent[p]
                path.reverse()
                return path, attach_start[path[0]], nb

        if dist >= max_dist or len(parent) >= max_visit:
            continue
        for dx, dy, dz in neigh:
            n = (cx + dx, cy + dy, cz + dz)
            if n in free and n not in parent and n not in start_set:
                parent[n] = cur
                attach_start[n] = attach_start[cur]
                q.append((n, dist + 1))
    return [], None, None


def _join_nearby_components(
    placements: list[Placement],
    existing: list[Brick],
    solid: SolidCells,
    *,
    staple_color: int,
    plate_color: int,
    staple_vox: set[tuple[int, int, int]],
    max_dist: int = 40,
) -> list[Brick]:
    """Connect each small component to the largest via a short solid fill."""
    shell = placements_to_bricks(placements)
    world = list(shell) + list(existing)
    before = check_connectivity(world).section_count
    if before <= 1:
        return []
    occupied = _placement_voxels(placements)
    free = solid - occupied - staple_vox

    report = check_connectivity(world)
    vsec: dict[tuple[int, int, int], int] = {}
    for i, p in enumerate(placements):
        for x, z in _footprint_cells(p):
            vsec[(x, p.iy, z)] = report.component_of[i]
    for i, b in enumerate(world):
        cell = _1x1_brick_voxel(b)
        if cell is not None and cell in staple_vox:
            vsec[cell] = report.component_of[i]

    by_sec: dict[int, list[tuple[int, int, int]]] = {}
    for cell, sec in vsec.items():
        by_sec.setdefault(sec, []).append(cell)
    if len(by_sec) < 2:
        return []

    added: list[Brick] = []
    # Cap attempts so this can't run away on hard geometry
    for _attempt in range(24):
        if before <= 1 or len(by_sec) < 2:
            break
        largest = max(by_sec, key=lambda s: len(by_sec[s]))
        goals = by_sec[largest]
        goal_set = set(goals)
        small = min(
            (s for s in by_sec if s != largest),
            key=lambda s: len(by_sec[s]),
        )
        members = by_sec[small]

        # Same-layer contact: just a 1x2 plate, no fill
        contact_plate = None
        contact_pair = None
        for a in members:
            ax, ay, az = a
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                b = (ax + dx, ay, az + dz)
                if b in goal_set:
                    contact_plate = _plate_1x2_on_pair(a, b, plate_color)
                    if contact_plate is not None:
                        contact_pair = (a, b)
                        break
            if contact_plate is not None:
                break
        if contact_plate is not None:
            snap = len(world)
            world.append(contact_plate)
            new_sec = check_connectivity(world).section_count
            if new_sec < before:
                added.append(contact_plate)
                before = new_sec
                print(f"    nearby plate -> {new_sec} sections")
                if before <= 1:
                    break
                report = check_connectivity(world)
                vsec = {}
                for i, p in enumerate(placements):
                    for x, z in _footprint_cells(p):
                        vsec[(x, p.iy, z)] = report.component_of[i]
                for i, br in enumerate(world):
                    cell = _1x1_brick_voxel(br)
                    if cell is not None and cell in staple_vox:
                        vsec[cell] = report.component_of[i]
                by_sec = {}
                for cell, s in vsec.items():
                    by_sec.setdefault(s, []).append(cell)
                continue
            world.pop()

        fill, a, b = _bfs_fill_path(members[:80], goals, free, max_dist=max_dist)
        if not fill or a is None or b is None:
            others = [s for s in by_sec if s != largest and s != small]
            if not others:
                print(f"    nearby join stuck at {before} sections")
                break
            small = min(others, key=lambda s: len(by_sec[s]))
            members = by_sec[small]
            fill, a, b = _bfs_fill_path(
                members[:80], goals, free, max_dist=max_dist
            )
            if not fill or a is None or b is None:
                print(f"    nearby join stuck at {before} sections")
                break

        snap = len(world)
        for fx, fy, fz in fill:
            world.append(_make_1x1_brick(staple_color, fx, fy, fz))
            free.discard((fx, fy, fz))

        chain = [a] + fill + [b]
        for i in range(len(chain) - 1):
            plate = _plate_1x2_on_pair(chain[i], chain[i + 1], plate_color)
            if plate is not None:
                world.append(plate)

        new_sec = check_connectivity(world).section_count
        if new_sec < before:
            for fx, fy, fz in fill:
                staple_vox.add((fx, fy, fz))
            added.extend(world[snap:])
            before = new_sec
            print(f"    nearby path +{len(fill)} -> {new_sec} sections")
            if before <= 1:
                break
            report = check_connectivity(world)
            vsec = {}
            for i, p in enumerate(placements):
                for x, z in _footprint_cells(p):
                    vsec[(x, p.iy, z)] = report.component_of[i]
            for i, br in enumerate(world):
                cell = _1x1_brick_voxel(br)
                if cell is not None and cell in staple_vox:
                    vsec[cell] = report.component_of[i]
            by_sec = {}
            for cell, s in vsec.items():
                by_sec.setdefault(s, []).append(cell)
        else:
            while len(world) > snap:
                world.pop()
            for fx, fy, fz in fill:
                free.add((fx, fy, fz))
            break
    return added


def finish_shell_surface(
    placements: list[Placement],
    *,
    shell_color: int = 15,
    tile_color: int = 15,
    plate_color: int = 72,
    staple_color: int = 71,
    solid: SolidCells | None = None,
) -> tuple[list[Brick], dict]:
    """under-plates → staples ↔ cavity-plates → exterior tiles."""
    shell = placements_to_bricks(
        [
            Placement(p.part_id, shell_color, p.ix, p.iy, p.iz, p.w, p.d, p.rot)
            for p in placements
        ]
    )
    sec0 = check_connectivity(shell).section_count

    under, _b, sec1 = bridge_under_with_plates(
        placements, [], plate_color=plate_color
    )

    cavity: list[Brick] = []
    staples: list[Brick] = []
    staple_vox: set[tuple[int, int, int]] = set()
    sec_cavity = sec1
    sec_staples = sec1

    if solid is not None:
        extras = list(under)
        # One-cell UPWARD thicken only — no AABB scan (cells are free solid)
        shell_vox = _placement_voxels(placements)
        free = solid - shell_vox
        thicken_bricks: list[Brick] = []
        for ix, iy, iz in shell_vox:
            above = (ix, iy + 1, iz)
            if above not in free:
                continue
            thicken_bricks.append(_make_1x1_brick(staple_color, ix, iy + 1, iz))
            staple_vox.add(above)
            free.discard(above)
        if thicken_bricks:
            staples.extend(thicken_bricks)
            print(f"    inward thicken +{len(thicken_bricks)} 1x1s")

        more_cavity, _, sec_cavity = bridge_tops_with_plates(
            placements,
            extras + staples,
            plate_color=plate_color,
            staple_vox=staple_vox,
        )
        if more_cavity:
            cavity.extend(more_cavity)
            extras = under + cavity

        stagnant = 0
        prev_sec = check_connectivity(shell + extras + staples).section_count
        for _alt in range(20):
            cur = check_connectivity(shell + extras + staples).section_count
            if cur <= 1:
                break

            improved = False

            new_staples, staple_vox, _s0, sec_staples = staple_vertical_gaps(
                placements,
                extras + staples,
                solid,
                staple_color=staple_color,
                plate_color=plate_color,
                max_rounds=4,
                prior_staple_vox=staple_vox,
            )
            if new_staples:
                staples.extend(new_staples)
                if sec_staples < cur:
                    improved = True
                    cur = sec_staples

            more_cavity, _, sec_cavity = bridge_tops_with_plates(
                placements,
                extras + staples,
                plate_color=plate_color,
                staple_vox=staple_vox,
            )
            if more_cavity and sec_cavity < cur:
                cavity.extend(more_cavity)
                extras = under + cavity
                improved = True
                cur = sec_cavity
            elif more_cavity and sec_cavity >= cur:
                # Plates that don't reduce sections — skip keeping them
                pass

            sec_before_under = cur
            more_under, _, sec_under = bridge_under_with_plates(
                placements, extras + staples, plate_color=plate_color
            )
            if more_under and sec_under < sec_before_under:
                under.extend(more_under)
                extras = under + cavity
                improved = True
                cur = sec_under

            if not improved:
                near = _join_nearby_components(
                    placements,
                    extras + staples,
                    solid,
                    staple_color=staple_color,
                    plate_color=plate_color,
                    staple_vox=staple_vox,
                    max_dist=48,
                )
                if near:
                    staples.extend(near)
                    print(f"    nearby joins +{len(near)}")
                    improved = True
                else:
                    spans = _bridge_air_gaps_with_plates(
                        placements,
                        extras + staples,
                        plate_color=plate_color,
                        staple_vox=staple_vox,
                    )
                    if spans:
                        cavity.extend(spans)
                        extras = under + cavity
                        improved = True
                        print(f"    air-span plates +{len(spans)}")
                    else:
                        air = _staple_air_column_gaps(
                            placements,
                            extras + staples,
                            staple_color=staple_color,
                            staple_vox=staple_vox,
                            max_gap=10,
                        )
                        if air:
                            staples.extend(air)
                            improved = True
                        else:
                            last = _staple_nearest_air_path(
                                placements,
                                extras + staples,
                                staple_color=staple_color,
                                plate_color=plate_color,
                                staple_vox=staple_vox,
                                max_dist=16,
                            )
                            if last:
                                staples.extend(last)
                                improved = True
                                print(f"    nearest-air +{len(last)}")

            new_sec = check_connectivity(shell + extras + staples).section_count
            if new_sec >= prev_sec:
                stagnant += 1
                if stagnant >= 3 or not improved:
                    break
            else:
                stagnant = 0
                prev_sec = new_sec

    tiles, uncovered = cover_exterior_with_tiles(
        placements,
        shell + under + cavity + staples,
        tile_color=tile_color,
        solid=solid,
    )
    # Fill leftover open studs (cavity / underside) with largest legal strips
    gap_plates = pack_open_stud_gaps(
        placements,
        shell + under + cavity + staples + tiles,
        plate_color=plate_color,
        solid=solid,
        staple_vox=staple_vox,
    )
    if gap_plates:
        cavity.extend(gap_plates)
        print(f"    gap-fill strips +{len(gap_plates)}")

    all_bricks = shell + under + cavity + staples + tiles
    sec2 = check_connectivity(all_bricks).section_count
    cols = count_collisions(all_bricks)

    stats = {
        "sections_before": sec0,
        "sections_after_under": sec1,
        "sections_after_cavity": sec_cavity,
        "sections_after_staples": sec_staples,
        "sections_final": sec2,
        "under_plates": len(under),
        "cavity_plates": len(cavity),
        "staples": len(staples),
        "tiles": len(tiles),
        "uncovered_studs": uncovered,
        "collisions": cols,
        "gap_fill_plates": len(gap_plates),
    }
    return all_bricks, stats


def pack_open_stud_gaps(
    placements: list[Placement],
    existing: list[Brick],
    *,
    plate_color: int = 72,
    solid: SolidCells | None = None,
    staple_vox: set[tuple[int, int, int]] | None = None,
) -> list[Brick]:
    """Pack largest collision-free plates onto remaining open tops (gap fill).

    Does not require multi-section spans — fills leftover runs where a strip fits.
    Skips exterior-facing cells (those are tiled separately).
    """
    staples = staple_vox or set()
    occ = _occupancy_by_layer(placements)
    for ix, iy, iz in staples:
        occ.setdefault(iy, set()).add((ix, iz))

    exterior = exterior_exposed_cells(placements, solid)
    free_by_layer: dict[int, dict[tuple[int, int], int]] = {}
    for iy, cells in occ.items():
        above = occ.get(iy + 1, set()) | {
            (x, z) for x, y, z in staples if y == iy + 1
        }
        ext = exterior.get(iy, set())
        free = {
            (x, z): 0
            for x, z in cells
            if (x, z) not in above and (x, z) not in ext
        }
        if free:
            free_by_layer[iy] = free

    if not free_by_layer:
        return []

    world = list(existing)
    index = CollisionWorld(world)
    used: dict[int, set[tuple[int, int]]] = {}
    plates, placed = _plate_bridge_round(
        free_by_layer=free_by_layer,
        used=used,
        world=world,
        index=index,
        origin_y_fn=lambda iy: _brick_top_y(iy) - PLATE_H,
        plate_color=plate_color,
        require_multi_section=False,
    )
    if placed:
        print(f"    packed open-stud gaps +{placed}")
    return plates


def open_cutaway_bricks(bricks: list[Brick], *, gap_studs: float = 2.0) -> list[Brick]:
    if not bricks:
        return []
    xs = [b.x for b in bricks]
    cut = 0.5 * (min(xs) + max(xs)) - gap_studs * STUD
    return [b for b in bricks if b.x <= cut]


def report_model_collisions(bricks: list[Brick]) -> int:
    return count_collisions(bricks)


def bridge_with_plates(
    placements: list[Placement],
    *,
    tile_color: int = 15,
    plate_color: int = 72,
    max_rounds: int = 40,
    solid: SolidCells | None = None,
) -> tuple[list[Brick], list[Brick], int, int]:
    del max_rounds
    all_bricks, stats = finish_shell_surface(
        placements, tile_color=tile_color, plate_color=plate_color, solid=solid
    )
    extras = all_bricks[len(placements_to_bricks(placements)) :]
    return (
        all_bricks,
        extras,
        stats["sections_before"],
        stats["sections_final"],
    )
