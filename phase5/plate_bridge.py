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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase2"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase4"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import (  # noqa: E402
    BRICK_H,
    PLATE_H,
    STUD,
    YAW_90,
    YAW_180,
    YAW_270,
    packing_templates,
)
from export_io import Brick  # noqa: E402
from greedy import IDENTITY, Placement, placements_to_bricks  # noqa: E402
from connectivity import (  # noqa: E402
    check_connectivity,
    clutch_strength,
    stud_overlap_count,
)
from brick_collision import (  # noqa: E402
    CollisionWorld,
    collides_any,
    count_collisions,
    strip_colliding_extras,
)


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
    solid: SolidCells | None = None,
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
    solid: SolidCells | None = None,
    cavity_only: bool = False,
) -> tuple[list[Brick], int, int]:
    """
    Studded plates on open tops spanning ≥2 sections.

    When cavity_only=True and solid is set, only tops facing into the solid
    (cavity) are plated — not exterior nubs.
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

    def _allow_top(ix: int, iy: int, iz: int) -> bool:
        if not cavity_only or solid is None:
            return True
        return (ix, iy + 1, iz) in solid

    exposed: dict[int, set[tuple[int, int]]] = {}
    for iy, cells in occ.items():
        above = occ.get(iy + 1, set()) | {
            (x, z) for x, y, z in staples if y == iy + 1
        }
        free = {
            (x, z)
            for x, z in cells
            if (x, z) not in above and _allow_top(x, iy, z)
        }
        if free:
            exposed.setdefault(iy, set()).update(free)
    for ix, iy, iz in staples:
        above_shell = occ.get(iy + 1, set())
        if (ix, iz) in above_shell or (ix, iy + 1, iz) in staples:
            continue
        if not _allow_top(ix, iy, iz):
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
    """Plate-bridge cavity-facing open tops only (not exterior nubs)."""
    return bridge_tops_with_plates(
        placements,
        existing,
        plate_color=plate_color,
        max_rounds=max_rounds,
        staple_vox=staple_vox,
        solid=solid,
        cavity_only=True,
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


def _index_bricks_covering_cells(
    index: CollisionWorld,
    cells: set[tuple[int, int, int]],
) -> set[int]:
    """Brick indices in `index` whose 1x1 cell or multi-stud footprint hits cells."""
    from catalog import get_part

    ignore: set[int] = set()
    for i, b in enumerate(index.bricks):
        kind = get_part(b.part_id).kind
        if kind in ("plate", "tile"):
            continue
        one = _1x1_brick_voxel(b)
        if one is not None and one in cells:
            ignore.add(i)
            continue
        # Approximate footprint for larger bricks at this layer
        spec = get_part(b.part_id)
        studs = getattr(spec, "studs", None)
        if not studs:
            continue
        w, d = studs
        ix = int(round(b.x / STUD - w / 2.0))
        iz = int(round(b.z / STUD - d / 2.0))
        # rotation swap
        if abs(b.a) < 0.1 and abs(b.c) > 0.9:
            w, d = d, w
            ix = int(round(b.x / STUD - w / 2.0))
            iz = int(round(b.z / STUD - d / 2.0))
        iy = int(round(-b.y / BRICK_H - 1.0))
        for dx in range(w):
            for dz in range(d):
                if (ix + dx, iy, iz + dz) in cells:
                    ignore.add(i)
                    break
            else:
                continue
            break
    return ignore


def _plate_1x2_on_pair(
    c0: tuple[int, int, int],
    c1: tuple[int, int, int],
    plate_color: int,
    *,
    index: CollisionWorld | None = None,
    prefer_under: bool = True,
    world: list[Brick] | None = None,
) -> Brick | None:
    """1x2 plate on two same-layer orthogonally adjacent cells, or None.

    Tries under the bricks first by default — needed when both tops are buried
    by tiles/higher bricks (common for equator pole strips).
    When `world` is set, returns the first non-colliding pose that reduces
    clutch section count.
    """
    if c0[1] != c1[1]:
        return None
    yaw90 = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)
    y = c0[1]
    under = (
        _brick_bottom_y(y),  # flush under brick bottoms (face-touch, legal)
    )
    over = (
        _brick_top_y(y) - PLATE_H,
        _brick_top_y(y) - 2 * PLATE_H,
    )
    origins = under + over if prefer_under else over + under
    before = check_connectivity(world).section_count if world is not None else None
    ignore = (
        _index_bricks_covering_cells(index, {c0, c1}) if index is not None else set()
    )

    def consider(cand: Brick) -> Brick | None:
        if index is not None and index.collides_except(cand, ignore):
            return None
        if world is None or before is None:
            return cand
        if check_connectivity(world + [cand]).section_count < before:
            return cand
        return None

    if c0[2] == c1[2] and abs(c0[0] - c1[0]) == 1:
        for origin_y in origins:
            got = consider(
                _make_part(
                    "3023.dat",
                    plate_color,
                    min(c0[0], c1[0]),
                    c0[2],
                    2,
                    1,
                    IDENTITY,
                    origin_y,
                )
            )
            if got is not None:
                return got
        return None
    if c0[0] == c1[0] and abs(c0[2] - c1[2]) == 1:
        for origin_y in origins:
            got = consider(
                _make_part(
                    "3023.dat",
                    plate_color,
                    c0[0],
                    min(c0[2], c1[2]),
                    1,
                    2,
                    yaw90,
                    origin_y,
                )
            )
            if got is not None:
                return got
        return None
    return None


def _corner_plate_on_l(
    cells: set[tuple[int, int, int]],
    sections: dict[tuple[int, int, int], int],
    plate_color: int,
    *,
    index: CollisionWorld,
    prefer_multi_section: bool = True,
) -> Brick | None:
    """Place a 2x2 corner plate (2420) on an L of three same-layer cells.

    Prefers Ls that touch two or more clutch sections (bridges floaters).
    Tries top then under, all four yaw orientations.
    """
    if not cells:
        return None
    by_layer: dict[int, set[tuple[int, int]]] = {}
    for x, y, z in cells:
        by_layer.setdefault(y, set()).add((x, z))

    yaws = (IDENTITY, YAW_90, YAW_180, YAW_270)
    # Local studs for 2420 (stud units) → which offset from 2x2 min-corner
    # After yaw, map to world cells relative to origin corner (ix, iz).
    from connections import local_stud_xz
    from catalog import get_part
    from transform import Transform

    spec = get_part("2420.dat")
    candidates: list[tuple[int, Brick]] = []  # (n_sections, brick)

    for iy, xz in by_layer.items():
        if len(xz) < 3:
            continue
        ixs = [x for x, _ in xz]
        izs = [z for _, z in xz]
        for ix in range(min(ixs) - 1, max(ixs) + 1):
            for iz in range(min(izs) - 1, max(izs) + 1):
                for rot in yaws:
                    # Pose at center of 2x2 footprint
                    sx = (ix + 1.0) * STUD
                    sz = (iz + 1.0) * STUD
                    for origin_y in (
                        _brick_bottom_y(iy),
                        _brick_top_y(iy) - PLATE_H,
                        _brick_top_y(iy) - 2 * PLATE_H,
                    ):
                        a, b, c, d, e, f, g, h, i = rot
                        pose = Transform(
                            x=sx, y=origin_y, z=sz,
                            a=a, b=b, c=c, d=d, e=e, f=f, g=g, h=h, i=i,
                        )
                        world_cells: list[tuple[int, int, int]] = []
                        ok = True
                        for lx, lz in local_stud_xz(spec):
                            wx, _wy, wz = pose.apply(lx, 0.0, lz)
                            cx = int(round(wx / STUD - 0.5))
                            cz = int(round(wz / STUD - 0.5))
                            cell = (cx, iy, cz)
                            if cell not in cells:
                                ok = False
                                break
                            world_cells.append(cell)
                        if not ok or len(world_cells) != 3:
                            continue
                        secs = {sections[c] for c in world_cells if c in sections}
                        if prefer_multi_section and len(secs) < 2:
                            continue
                        brick = Brick(
                            part_id="2420.dat",
                            color=plate_color,
                            x=sx,
                            y=origin_y,
                            z=sz,
                            a=a, b=b, c=c, d=d, e=e, f=f, g=g, h=h, i=i,
                        )
                        if index.collides(brick):
                            continue
                        candidates.append((len(secs), brick))
                        break  # one origin_y per rot/pos is enough
    if not candidates:
        return None
    candidates.sort(key=lambda t: -t[0])
    return candidates[0][1]


def _span_plate_on_pair(
    c0: tuple[int, int, int],
    c1: tuple[int, int, int],
    plate_color: int,
    *,
    index: CollisionWorld | None = None,
    max_span: int = 6,
    prefer_under: bool = True,
    world: list[Brick] | None = None,
) -> Brick | None:
    """Axis-aligned plate spanning two same-layer cells (2–6 studs).

    Tries under then top origins by default (equator bridges).
    When `world` is set, requires a real section-count reduction.
    """
    if c0[1] != c1[1]:
        return None
    yaw90 = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)
    y = c0[1]
    under = (
        _brick_bottom_y(y),  # flush under — never -PLATE_H (that embeds into brick)
    )
    over = (
        _brick_top_y(y) - PLATE_H,
        _brick_top_y(y) - 2 * PLATE_H,
    )
    origins = under + over if prefer_under else over + under
    part_for = {2: "3023.dat", 3: "3623.dat", 4: "3710.dat", 6: "3666.dat"}
    before = check_connectivity(world).section_count if world is not None else None
    span_cells: set[tuple[int, int, int]] = {c0, c1}
    if c0[2] == c1[2]:
        a0, a1 = sorted((c0[0], c1[0]))
        span_cells = {(x, c0[1], c0[2]) for x in range(a0, a1 + 1)}
    elif c0[0] == c1[0]:
        a0, a1 = sorted((c0[2], c1[2]))
        span_cells = {(c0[0], c0[1], z) for z in range(a0, a1 + 1)}
    ignore = (
        _index_bricks_covering_cells(index, span_cells) if index is not None else set()
    )

    def consider(cand: Brick) -> Brick | None:
        if index is not None and index.collides_except(cand, ignore):
            return None
        if world is None or before is None:
            return cand
        if check_connectivity(world + [cand]).section_count < before:
            return cand
        return None

    def try_span(along_x: bool) -> Brick | None:
        if along_x:
            if c0[2] != c1[2]:
                return None
            a0, a1 = sorted((c0[0], c1[0]))
            span = a1 - a0 + 1
            if span not in part_for or span > max_span:
                return None
            part = part_for[span]
            for origin_y in origins:
                got = consider(
                    _make_part(
                        part, plate_color, a0, c0[2], span, 1, IDENTITY, origin_y
                    )
                )
                if got is not None:
                    return got
            return None
        if c0[0] != c1[0]:
            return None
        a0, a1 = sorted((c0[2], c1[2]))
        span = a1 - a0 + 1
        if span not in part_for or span > max_span:
            return None
        part = part_for[span]
        for origin_y in origins:
            got = consider(
                _make_part(
                    part, plate_color, c0[0], a0, 1, span, yaw90, origin_y
                )
            )
            if got is not None:
                return got
        return None

    return try_span(True) or try_span(False)


def _plate_clutch_score(plate: Brick, world: list[Brick]) -> int:
    """Total stud overlaps between a candidate plate and existing bricks."""
    total = 0
    for b in world:
        total += stud_overlap_count(plate, b)
        total += stud_overlap_count(b, plate)
    return total


def _best_plate_between_sections(
    members: list[tuple[int, int, int]],
    goals: list[tuple[int, int, int]],
    plate_color: int,
    *,
    index: CollisionWorld,
    max_span: int = 6,
    world: list[Brick] | None = None,
) -> Brick | None:
    """Best plate joining member→goal cells by stud-overlap score.

    Prefers multi-stud clutch with neighbors; span length and under-pose are
    tie-breakers. Only returns a plate that reduces section count when `world`
    is provided (via the plate constructors' section checks).
    """
    goal_set = set(goals)
    pairs: list[tuple[int, tuple[int, int, int], tuple[int, int, int]]] = []
    for a in members:
        ax, ay, az = a
        for b in goals:
            if b[1] != ay:
                continue
            if az == b[2] and 0 < abs(ax - b[0]) < max_span:
                pairs.append((abs(ax - b[0]) + 1, a, b))
            elif ax == b[0] and 0 < abs(az - b[2]) < max_span:
                pairs.append((abs(az - b[2]) + 1, a, b))
    pairs.sort(key=lambda t: -t[0])

    best: Brick | None = None
    best_score = -1

    def _score(span: int, plate: Brick, iy: int) -> int:
        under = abs(plate.y - _brick_bottom_y(iy)) < 0.5
        # Heavy weight on real stud overlap; demote single-stud-only joins.
        overlap = _plate_clutch_score(plate, world) if world is not None else span
        if overlap <= 1 and span <= 2:
            overlap_term = overlap  # strongly demote 1-stud bridges
        else:
            overlap_term = overlap * 20
        return overlap_term + span * 10 + (5 if under else 0)

    for span, a, b in pairs:
        if span == 2:
            cand = _plate_1x2_on_pair(
                a, b, plate_color, index=index, world=world
            )
        else:
            cand = _span_plate_on_pair(
                a, b, plate_color, index=index, max_span=max_span, world=world
            )
        if cand is None:
            continue
        sc = _score(span, cand, a[1])
        if sc > best_score:
            best_score = sc
            best = cand
    if best is not None:
        return best
    for a in members:
        ax, ay, az = a
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            b = (ax + dx, ay, az + dz)
            if b in goal_set:
                cand = _plate_1x2_on_pair(
                    a, b, plate_color, index=index, world=world
                )
                if cand is not None:
                    return cand
    return None


def _filter_exterior_staples(
    shell: list[Brick],
    extras: list[Brick],
    solid: SolidCells,
    shell_vox: set[tuple[int, int, int]],
) -> tuple[list[Brick], int]:
    """Drop 1x1 staples whose cells lie outside the solid∪shell volume.

    Keeps the filter only when clutch section count does not worsen.
    """
    before = check_connectivity(shell + extras).section_count
    allowed = solid | shell_vox
    kept: list[Brick] = []
    dropped = 0
    for b in extras:
        cell = _1x1_brick_voxel(b)
        if cell is not None and cell not in allowed:
            dropped += 1
            continue
        kept.append(b)
    if dropped == 0:
        return extras, 0
    after = check_connectivity(shell + kept).section_count
    if after > before:
        return extras, 0
    return kept, dropped


def _brick_part_for_span(w: int, d: int) -> str | None:
    """Catalog brick id for an axis-aligned 1×N footprint."""
    n = w if d == 1 else d if w == 1 else 0
    return {1: "3005.dat", 2: "3004.dat", 4: "3010.dat", 6: "3009.dat"}.get(n)


def _pack_staple_cells_longest(
    cells: set[tuple[int, int, int]],
    color: int,
    *,
    probe: CollisionWorld,
    partial: bool = False,
) -> list[Brick] | None:
    """Greedy longest 1×N bricks over cells.

    If partial=False (default), returns None when any cell cannot be placed.
    If partial=True, skips cells that cannot be placed and returns what fits.
    """
    yaw90 = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)
    remaining = set(cells)
    out: list[Brick] = []
    lengths = (6, 4, 2, 1)
    while remaining:
        ix, iy, iz = min(remaining)
        placed = False
        for length in lengths:
            part = _brick_part_for_span(length, 1)
            if part is None:
                continue
            run_x = [(ix + k, iy, iz) for k in range(length)]
            if all(c in remaining for c in run_x):
                brick = _make_part(
                    part, color, ix, iz, length, 1, IDENTITY, _brick_top_y(iy)
                )
                if not probe.collides(brick):
                    out.append(brick)
                    probe.add(brick)
                    remaining.difference_update(run_x)
                    placed = True
                    break
            if length == 1:
                continue
            run_z = [(ix, iy, iz + k) for k in range(length)]
            if all(c in remaining for c in run_z):
                brick = _make_part(
                    part, color, ix, iz, 1, length, yaw90, _brick_top_y(iy)
                )
                if not probe.collides(brick):
                    out.append(brick)
                    probe.add(brick)
                    remaining.difference_update(run_z)
                    placed = True
                    break
        if not placed:
            if partial:
                remaining.discard((ix, iy, iz))
                continue
            return None
    return out


def _merge_adjacent_1x1_staples(
    shell: list[Brick],
    extras: list[Brick],
    *,
    staple_color: int,
) -> tuple[list[Brick], int]:
    """Bond-merge 1x1 staples into longest 1×N bricks when 1/0 holds.

    Prefers merges that do not worsen clutch mean overlap / weak-edge count.
    """
    before_sec = check_connectivity(shell + extras).section_count
    if before_sec != 1:
        return extras, 0
    before_str = clutch_strength(shell + extras)
    before_cols = count_collisions(shell + extras)

    cells: dict[tuple[int, int, int], int] = {}
    for i, b in enumerate(extras):
        cell = _1x1_brick_voxel(b)
        if cell is not None:
            cells[cell] = i
    if len(cells) < 2:
        return extras, 0

    non_1x1 = [b for i, b in enumerate(extras) if i not in cells.values()]
    probe = CollisionWorld(shell + non_1x1)
    packed = _pack_staple_cells_longest(set(cells), staple_color, probe=probe)
    if packed is None:
        return extras, 0

    n_merged = sum(1 for b in packed if b.part_id != "3005.dat")
    if n_merged == 0:
        return extras, 0

    kept = non_1x1 + packed
    after_sec = check_connectivity(shell + kept).section_count
    if after_sec > 1:
        return extras, 0
    after_cols = count_collisions(shell + kept)
    if after_cols > before_cols:
        return extras, 0
    after_str = clutch_strength(shell + kept)
    # Accept if weak edges drop, or mean overlap rises, or part count drops
    # without making strength worse.
    if after_str.weak_edges > before_str.weak_edges and (
        after_str.mean_overlap + 1e-9 < before_str.mean_overlap
    ):
        return extras, 0
    return kept, n_merged


def _bond_strengthen_pass(
    shell: list[Brick],
    extras: list[Brick],
    *,
    staple_color: int,
) -> tuple[list[Brick], int]:
    """Post-PASS: merge 1x1 staple runs for multi-stud vertical coverage."""
    return _merge_adjacent_1x1_staples(
        shell, extras, staple_color=staple_color
    )


# Soft gate: only attempt hollow thicken when many joins are 1-stud.
_WEAK_RATIO_THICKEN = 0.45


def _brick_footprint_voxels(b: Brick) -> set[tuple[int, int, int]]:
    """Stud cells occupied by a brick-kind part (empty for plates/tiles)."""
    from catalog import get_part

    spec = get_part(b.part_id)
    if spec.kind != "brick":
        return set()
    w, d = spec.width, spec.depth
    yaw90 = abs(b.a) < 0.1 and abs(b.g) > 0.9
    if yaw90:
        w, d = d, w
    ix0 = int(round(b.x / STUD - w / 2.0))
    iz0 = int(round(b.z / STUD - d / 2.0))
    iy = int(round(-b.y / BRICK_H - 1.0))
    return {
        (x, iy, z)
        for x in range(ix0, ix0 + w)
        for z in range(iz0, iz0 + d)
    }


def _try_inward_hollow_thicken(
    shell: list[Brick],
    extras: list[Brick],
    *,
    solid: SolidCells | None,
    shell_vox: set[tuple[int, int, int]],
    staple_color: int,
    staple_vox: set[tuple[int, int, int]],
) -> tuple[list[Brick], int]:
    """If weak joins dominate, add one inward solid ring (still hollow cavity).

    Keeps the change only when section count stays 1, collisions do not rise,
    and clutch strength improves (fewer weak edges or higher mean overlap).
    """
    if solid is None:
        return extras, 0
    world = shell + extras
    if check_connectivity(world).section_count != 1:
        return extras, 0
    before = clutch_strength(world)
    if before.edge_count <= 0 or before.weak_ratio < _WEAK_RATIO_THICKEN:
        return extras, 0
    before_cols = count_collisions(world)

    occupied = set(shell_vox) | set(staple_vox)
    for b in shell:
        occupied |= _brick_footprint_voxels(b)
    for b in extras:
        occupied |= _brick_footprint_voxels(b)

    neigh = (
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1),
    )
    candidates: set[tuple[int, int, int]] = set()
    for ix, iy, iz in occupied:
        for dx, dy, dz in neigh:
            n = (ix + dx, iy + dy, iz + dz)
            if n in solid and n not in occupied:
                candidates.add(n)
    if not candidates:
        return extras, 0

    probe = CollisionWorld(world)
    packed = _pack_staple_cells_longest(
        candidates,
        staple_color,
        probe=probe,
        partial=True,
    )
    if not packed:
        return extras, 0

    # Prefer longer bricks first; only keep those that clutch into the model.
    packed.sort(key=lambda b: -len(_brick_footprint_voxels(b)))
    kept_extra = list(extras)
    world_now = list(shell) + kept_extra
    added = 0
    for brick in packed:
        if not any(
            stud_overlap_count(b, brick) >= 1 or stud_overlap_count(brick, b) >= 1
            for b in world_now
        ):
            continue
        trial = kept_extra + [brick]
        if count_collisions(shell + trial) > before_cols:
            continue
        kept_extra = trial
        world_now.append(brick)
        added += 1
    if added == 0:
        return extras, 0
    if check_connectivity(shell + kept_extra).section_count != 1:
        return extras, 0

    after = clutch_strength(shell + kept_extra)
    improved = (
        after.weak_ratio < before.weak_ratio - 1e-6
        or after.mean_overlap > before.mean_overlap + 1e-9
        or after.weak_edges < before.weak_edges
    )
    if not improved:
        return extras, 0
    return kept_extra, added


def _prune_redundant_staples(
    shell: list[Brick], extras: list[Brick]
) -> tuple[list[Brick], int]:
    """Remove 1x1 staples that are not needed to keep a single clutch section.

    Keeps all plates/tiles. Tries removing staples largest-index-first so late
    fills (spine-nuke) go before structural thicken when possible.
    """
    from catalog import get_part

    if check_connectivity(shell + extras).section_count != 1:
        return extras, 0

    plates_tiles = [b for b in extras if get_part(b.part_id).kind in ("plate", "tile")]
    staples = [b for b in extras if get_part(b.part_id).kind not in ("plate", "tile")]
    if not staples:
        return extras, 0

    kept = list(staples)
    removed = 0
    # Multiple passes: removing one staple can free another
    for _pass in range(4):
        progressed = False
        i = len(kept) - 1
        while i >= 0:
            trial = kept[:i] + kept[i + 1 :]
            if check_connectivity(shell + plates_tiles + trial).section_count == 1:
                kept = trial
                removed += 1
                progressed = True
            i -= 1
        if not progressed:
            break
    return plates_tiles + kept, removed


def _prune_colliding_plates(
    shell: list[Brick], extras: list[Brick]
) -> tuple[list[Brick], int]:
    """Remove plates/tiles that AABB-collide, if single-section connectivity holds."""
    from catalog import get_part

    if check_connectivity(shell + extras).section_count != 1:
        return extras, 0

    staples = [b for b in extras if get_part(b.part_id).kind not in ("plate", "tile")]
    strips = [b for b in extras if get_part(b.part_id).kind in ("plate", "tile")]
    kept = list(strips)
    removed = 0
    i = 0
    while i < len(kept):
        b = kept[i]
        # Does b collide with shell+staples+other kept strips?
        others = shell + staples + kept[:i] + kept[i + 1 :]
        if collides_any(b, others):
            trial = staples + kept[:i] + kept[i + 1 :]
            if check_connectivity(shell + trial).section_count == 1:
                kept = kept[:i] + kept[i + 1 :]
                removed += 1
                continue
        i += 1
    return staples + kept, removed


def _exhaustive_contact_plates(
    placements: list[Placement],
    existing: list[Brick],
    *,
    plate_color: int,
    staple_vox: set[tuple[int, int, int]],
) -> list[Brick]:
    """Try every same-layer multi-section adjacency with under/top/span plates.

    Last plate-first pass before spine-nuke — catches equator poles etc.
    """
    shell = placements_to_bricks(placements)
    world = list(shell) + list(existing)
    before = check_connectivity(world).section_count
    if before <= 1:
        return []

    index = CollisionWorld(world)
    added: list[Brick] = []

    def refresh() -> tuple[
        dict[tuple[int, int, int], int], dict[int, list[tuple[int, int, int]]], int
    ]:
        report = check_connectivity(world)
        vsec: dict[tuple[int, int, int], int] = {}
        for i, p in enumerate(placements):
            for x, z in _footprint_cells(p):
                vsec[(x, p.iy, z)] = report.component_of[i]
        for i, b in enumerate(world):
            cell = _1x1_brick_voxel(b)
            if cell is not None and cell in staple_vox:
                vsec[cell] = report.component_of[i]
        by: dict[int, list[tuple[int, int, int]]] = {}
        for cell, sec in vsec.items():
            by.setdefault(sec, []).append(cell)
        return vsec, by, report.section_count

    failed_small: set[int] = set()
    for _round in range(200):
        vsec, by_sec, nsec = refresh()
        before = nsec
        if nsec <= 1:
            break
        largest = max(by_sec, key=lambda s: len(by_sec[s]))
        goals = by_sec[largest]
        smalls = [s for s in by_sec if s != largest and s not in failed_small]
        if not smalls:
            break
        small = min(smalls, key=lambda s: len(by_sec[s]))
        plate = _best_plate_between_sections(
            by_sec[small],
            goals,
            plate_color,
            index=index,
            max_span=6,
            world=world,
        )
        if plate is None:
            plate = _corner_plate_on_l(
                set(vsec.keys()), vsec, plate_color, index=index
            )
        if plate is None:
            failed_small.add(small)
            continue
        world.append(plate)
        index.add(plate)
        after = check_connectivity(world).section_count
        if after < before:
            added.append(plate)
            failed_small.clear()
            print(f"    exhaust plate -> {after} sections")
            continue
        world.pop()
        index.truncate(len(index.bricks) - 1)
        failed_small.add(small)
    return added


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
    index = CollisionWorld(world)

    for y, cells in sorted(by_layer.items()):
        layer_used = used.setdefault(y, set())
        items = list(cells.items())
        # Prefer longer spans first (stronger multi-stud bridges)
        for span in range(max_span, 1, -1):
            made = True
            while made:
                made = False
                report = check_connectivity(world)
                if report.section_count <= 1:
                    return added
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
                            (x, y, z),
                            nb,
                            plate_color,
                            index=index,
                            max_span=max_span,
                            world=world,
                        )
                        if plate is None:
                            continue
                        world.append(plate)
                        index.add(plate)
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
                        index.truncate(len(index.bricks) - 1)
                    if made:
                        break
    return added


def _connector_allowed_cells(
    solid: SolidCells,
    shell_vox: set[tuple[int, int, int]],
) -> set[tuple[int, int, int]]:
    """Solid ∪ shell ∪ 2-cell shell halo.

    Air connectors may hug the shell surface (needed for equator joins) but
    must not float far outside the sphere.
    """
    allowed = set(solid) | set(shell_vox)
    neigh = (
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (0, 0, 1),
        (0, 0, -1),
    )
    frontier = set(shell_vox)
    for _ in range(2):
        nxt: set[tuple[int, int, int]] = set()
        for x, y, z in frontier:
            for dx, dy, dz in neigh:
                c = (x + dx, y + dy, z + dz)
                if c not in allowed:
                    allowed.add(c)
                    nxt.add(c)
        frontier = nxt
    return allowed


def _staple_air_column_gaps(
    placements: list[Placement],
    existing: list[Brick],
    *,
    staple_color: int,
    staple_vox: set[tuple[int, int, int]],
    max_gap: int = 6,
    solid: SolidCells | None = None,
) -> list[Brick]:
    """Fill short same-column gaps between different sections.

    When `solid` is set, mid cells must lie inside the voxel solid (no exterior
    floating 1x1s outside the sphere).
    """
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
            if solid is not None and any(c not in solid for c in mids):
                continue
            candidates.append((gap, ix, iz, a, b, sa, sb))
    candidates.sort()

    added: list[Brick] = []
    index = CollisionWorld(world)
    for gap, ix, iz, a, b, sa, sb in candidates:
        if find(sa) == find(sb):
            continue
        snap_w, snap_a = len(world), len(added)
        snap_v = set(staple_vox)
        snap_boxes = len(index.boxes)
        ok = True
        occ_now = set(vsec) | set(staple_vox)
        for iy in range(a + 1, b):
            cell = (ix, iy, iz)
            if cell in occ_now or (solid is not None and cell not in solid):
                ok = False
                break
            brick = _make_1x1_brick(staple_color, ix, iy, iz)
            # Never punch plates/tiles; ignore brick-AABB false positives
            if index.collides_flat(brick):
                ok = False
                break
            world.append(brick)
            index.add(brick)
            added.append(brick)
            staple_vox.add(cell)
            occ_now.add(cell)
        if not ok:
            while len(world) > snap_w:
                world.pop()
            del added[snap_a:]
            staple_vox.clear()
            staple_vox.update(snap_v)
            index.truncate(snap_boxes)
            continue
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
        index.truncate(snap_boxes)
    return added


def _staple_nearest_air_path(
    placements: list[Placement],
    existing: list[Brick],
    *,
    staple_color: int,
    plate_color: int,
    staple_vox: set[tuple[int, int, int]],
    max_dist: int = 16,
    solid: SolidCells | None = None,
) -> list[Brick]:
    """Connect smallest→largest via a short L-path of 1x1s inside `solid`."""
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
                if solid is not None and cell not in solid:
                    return []
                fill.append(cell)
        return fill

    fill = try_path("yxz") or try_path("xyz") or try_path("xzy")
    if not fill:
        return []

    index = CollisionWorld(world)
    snap = len(world)
    added: list[Brick] = []
    ok = True
    occ_now = set(vsec) | set(staple_vox)
    for fx, fy, fz in fill:
        cell = (fx, fy, fz)
        if cell in occ_now or (solid is not None and cell not in solid):
            ok = False
            break
        brick = _make_1x1_brick(staple_color, fx, fy, fz)
        if index.collides_flat(brick):
            ok = False
            break
        world.append(brick)
        index.add(brick)
        added.append(brick)
        staple_vox.add(cell)
        occ_now.add(cell)
    if ok:
        chain = [a] + fill + [b]
        for i in range(len(chain) - 1):
            plate = _plate_1x2_on_pair(
                chain[i], chain[i + 1], plate_color, index=index
            )
            if plate is None:
                continue
            world.append(plate)
            index.add(plate)
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
    index = CollisionWorld(world)
    failed_small: set[int] = set()
    for _attempt in range(400):
        if before <= 1 or len(by_sec) < 2:
            break
        largest = max(by_sec, key=lambda s: len(by_sec[s]))
        goals = by_sec[largest]
        goal_set = set(goals)
        candidates = [s for s in by_sec if s != largest and s not in failed_small]
        if not candidates:
            print(f"    nearby join stuck at {before} sections")
            break
        small = min(candidates, key=lambda s: len(by_sec[s]))
        members = by_sec[small]

        # Plate-first: longest span / under-top contact between small and large
        contact_plate = _best_plate_between_sections(
            members, goals, plate_color, index=index, max_span=6, world=world
        )
        if contact_plate is not None:
            world.append(contact_plate)
            index.add(contact_plate)
            new_sec = check_connectivity(world).section_count
            if new_sec < before:
                added.append(contact_plate)
                before = new_sec
                failed_small.clear()
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
            index.truncate(len(index.bricks) - 1)

        # L-corner plate when three cells form a multi-section L
        corner = _corner_plate_on_l(
            set(vsec.keys()),
            vsec,
            plate_color,
            index=index,
            prefer_multi_section=True,
        )
        if corner is not None:
            world.append(corner)
            index.add(corner)
            new_sec = check_connectivity(world).section_count
            if new_sec < before:
                added.append(corner)
                before = new_sec
                failed_small.clear()
                print(f"    nearby corner -> {new_sec} sections")
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
            index.truncate(len(index.bricks) - 1)

        fill, a, b = _bfs_fill_path(members[:80], goals, free, max_dist=max_dist)
        if not fill or a is None or b is None:
            # Fallback: short air/empty L-path to nearest goal cell
            best = None
            best_d = 10**9
            for aa in members[:40]:
                for bb in goals[:: max(1, len(goals) // 80)]:
                    d = abs(aa[0] - bb[0]) + abs(aa[1] - bb[1]) + abs(aa[2] - bb[2])
                    if 1 < d < best_d:
                        best_d = d
                        best = (aa, bb)
            fill, a, b = [], None, None
            if best is not None and best_d <= max_dist:
                a, b = best
                occ = set(vsec) | set(staple_vox)

                def air_path(order: str) -> list[tuple[int, int, int]]:
                    cells: list[tuple[int, int, int]] = []
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
                                return cells
                            # Stay inside solid free space (no exterior air fills)
                            if cell in occ or cell not in free:
                                return []
                            cells.append(cell)
                    return cells

                fill = air_path("yxz") or air_path("xyz") or air_path("xzy")
            if not fill or a is None or b is None:
                failed_small.add(small)
                continue

        snap = len(world)
        snap_idx = len(index.bricks)
        ok = True
        # Collision-check 1x1s against plates/tiles only (not brick AABB FPs).
        # Prefer plates earlier in this function; 1x1 paths are last resort and
        # get bond-merged into longer bricks after we reach 1 section.
        occ_now = set(vsec) | set(staple_vox)
        for fx, fy, fz in fill:
            cell = (fx, fy, fz)
            if cell in occ_now:
                ok = False
                break
            brick = _make_1x1_brick(staple_color, fx, fy, fz)
            if index.collides_flat(brick):
                ok = False
                break
            world.append(brick)
            index.add(brick)
            occ_now.add(cell)
            free.discard(cell)

        if ok:
            chain = [a] + fill + [b]
            for i in range(len(chain) - 1):
                plate = _plate_1x2_on_pair(
                    chain[i], chain[i + 1], plate_color, index=index
                )
                if plate is None:
                    continue
                world.append(plate)
                index.add(plate)

        new_sec = check_connectivity(world).section_count if ok else before
        if ok and new_sec < before:
            for fx, fy, fz in fill:
                staple_vox.add((fx, fy, fz))
            added.extend(world[snap:])
            before = new_sec
            failed_small.clear()
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
            index.truncate(snap_idx)
            for fx, fy, fz in fill:
                free.add((fx, fy, fz))
            failed_small.add(small)
    return added


def _reconnect_spine_clear_plates(
    placements: list[Placement],
    existing: list[Brick],
    *,
    staple_color: int,
    staple_vox: set[tuple[int, int, int]],
    max_gap: int = 24,
    solid: SolidCells | None = None,
) -> tuple[list[Brick], list[Brick]]:
    """Fill same-column gaps, dropping only plates that block each fill.

    Keeps unrelated plate connectors. Returns (new_staples, new_extras) or
    ([], existing) if section count does not improve.
    """
    from catalog import get_part

    from brick_collision import brick_aabb

    shell = placements_to_bricks(placements)
    world = list(shell) + list(existing)
    before0 = check_connectivity(world).section_count
    if before0 <= 1:
        return [], existing

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

    occupied = set(vsec) | set(staple_vox)
    candidates: list[tuple[int, int, int, int, int, int, int]] = []
    for (ix, iz), heights in by_col.items():
        for a, b in zip(heights, heights[1:]):
            gap = b - a - 1
            if gap < 1 or gap > max_gap:
                continue
            sa, sb = vsec[(ix, a, iz)], vsec[(ix, b, iz)]
            if find(sa) == find(sb):
                continue
            mids = [(ix, iy, iz) for iy in range(a + 1, b)]
            if any(c in occupied for c in mids):
                continue
            if solid is not None and any(c not in solid for c in mids):
                continue
            candidates.append((gap, ix, iz, a, b, sa, sb))
    candidates.sort()

    plate_set = {b for b in existing if get_part(b.part_id).kind == "plate"}
    index = CollisionWorld(world)
    added: list[Brick] = []
    dropped: list[Brick] = []
    before = before0

    for gap, ix, iz, a, b, sa, sb in candidates:
        if find(sa) == find(sb):
            continue
        mids = [(ix, iy, iz) for iy in range(a + 1, b)]
        mid_bricks = [_make_1x1_brick(staple_color, x, y, z) for x, y, z in mids]

        conflict: list[Brick] = []
        for brick in mid_bricks:
            box = brick_aabb(brick)
            for ob, obox in zip(index.bricks, index.boxes):
                if ob not in plate_set:
                    continue
                if box.overlaps(obox) and ob not in conflict:
                    conflict.append(ob)

        snap_world = list(world)
        snap_vox = set(staple_vox)
        snap_dropped = list(dropped)

        if conflict:
            world = [br for br in world if br not in conflict]
            for p in conflict:
                plate_set.discard(p)
                dropped.append(p)
        index = CollisionWorld(world)
        ok = True
        occ_now = set(vsec) | set(staple_vox)
        batch: list[Brick] = []
        for cell, brick in zip(mids, mid_bricks):
            if cell in occ_now or index.collides_flat(brick):
                ok = False
                break
            world.append(brick)
            index.add(brick)
            batch.append(brick)
            staple_vox.add(cell)
            occ_now.add(cell)
        if not ok:
            world = snap_world
            staple_vox.clear()
            staple_vox.update(snap_vox)
            dropped[:] = snap_dropped
            plate_set = {
                b for b in existing if get_part(b.part_id).kind == "plate"
            } - set(dropped)
            index = CollisionWorld(world)
            continue

        after = check_connectivity(world).section_count
        if after < before:
            union(sa, sb)
            added.extend(batch)
            before = after
            print(f"    spine-fill +{gap} drop={len(conflict)} -> {after} sections")
            if before <= 1:
                break
            continue

        world = snap_world
        staple_vox.clear()
        staple_vox.update(snap_vox)
        dropped[:] = snap_dropped
        plate_set = {
            b for b in existing if get_part(b.part_id).kind == "plate"
        } - set(dropped)
        index = CollisionWorld(world)

    if before >= before0 or not added:
        return [], existing

    print(
        f"    spine-clear +{len(added)} dropped_plates={len(dropped)} "
        f"-> {before} sections"
    )
    drop_ids = {id(p) for p in dropped}
    new_extras = [b for b in existing if id(b) not in drop_ids] + added
    return added, new_extras


def _reconnect_spine_nuke_plates(
    placements: list[Placement],
    existing: list[Brick],
    *,
    staple_color: int,
    staple_vox: set[tuple[int, int, int]],
    max_gap: int = 16,
    solid: SolidCells | None = None,
) -> tuple[list[Brick], list[Brick]]:
    """Remove all plates, fill column spines, re-add non-colliding plates.

    Stronger than surgical clear — use when still fragmented after milder passes.
    """
    from catalog import get_part

    shell = placements_to_bricks(placements)
    before = check_connectivity(shell + existing).section_count
    if before <= 1:
        return [], existing

    plates = [b for b in existing if get_part(b.part_id).kind == "plate"]
    rest = [b for b in existing if get_part(b.part_id).kind != "plate"]
    air = _staple_air_column_gaps(
        placements,
        rest,
        staple_color=staple_color,
        staple_vox=staple_vox,
        max_gap=max_gap,
        solid=solid,
    )
    index = CollisionWorld(shell + rest + air)
    kept_plates: list[Brick] = []
    for p in plates:
        if index.collides(p):
            continue
        index.add(p)
        kept_plates.append(p)

    new_extras = rest + air + kept_plates
    after = check_connectivity(shell + new_extras).section_count
    if after >= before:
        for b in air:
            cell = _1x1_brick_voxel(b)
            if cell is not None:
                staple_vox.discard(cell)
        return [], existing

    dropped = len(plates) - len(kept_plates)
    print(
        f"    spine-nuke +{len(air)} dropped_plates={dropped} -> {after} sections"
    )
    return air, new_extras


def _discard_staple_cells(
    bricks: list[Brick], staple_vox: set[tuple[int, int, int]]
) -> None:
    for b in bricks:
        cell = _1x1_brick_voxel(b)
        if cell is not None:
            staple_vox.discard(cell)


def _keep_if_improves(
    shell: list[Brick],
    extras: list[Brick],
    batch: list[Brick],
    cur: int,
    staple_vox: set[tuple[int, int, int]],
    *,
    shell_vox: set[tuple[int, int, int]] | None = None,
    strip_new: bool = False,
) -> tuple[list[Brick], int, bool]:
    """Append batch only if section count drops; else discard staple cells."""
    if not batch:
        return extras, cur, False
    raw_nxt = check_connectivity(shell + extras + batch).section_count
    trial_batch = batch
    nxt = raw_nxt
    if strip_new:
        stripped, _r = strip_colliding_extras(shell + extras, batch)
        if stripped:
            stripped_nxt = check_connectivity(shell + extras + stripped).section_count
            # Never keep a stripped batch that undoes the bridge (e.g. 1→10)
            if stripped_nxt <= raw_nxt:
                trial_batch = stripped
                nxt = stripped_nxt
    if nxt >= cur:
        _discard_staple_cells(batch, staple_vox)
        return extras, cur, False
    extras = extras + trial_batch
    if shell_vox is not None:
        for b in trial_batch:
            cell = _1x1_brick_voxel(b)
            if cell is not None and cell not in shell_vox:
                staple_vox.add(cell)
    return extras, nxt, True


def _reconnect_plate_first(
    placements: list[Placement],
    extras: list[Brick],
    solid: SolidCells,
    *,
    plate_color: int,
    staple_color: int,
    staple_vox: set[tuple[int, int, int]],
    label: str = "reconnect",
    strip_new: bool = False,
    shell_vox: set[tuple[int, int, int]] | None = None,
) -> list[Brick]:
    """Plates → exhaust → MST → (air only if many sections) → spine-nuke.

    Air-column is skipped when few sections remain — it thrash-fills and
    never reaches nuke, which is what closes the last floaters.
    """
    shell = placements_to_bricks(placements)
    if shell_vox is None:
        shell_vox = _placement_voxels(placements)

    for _fin in range(16):
        cur = check_connectivity(shell + extras).section_count
        if cur <= 1:
            break

        spans = _bridge_air_gaps_with_plates(
            placements,
            extras,
            plate_color=plate_color,
            staple_vox=staple_vox,
            max_span=6,
        )
        extras, cur, ok = _keep_if_improves(
            shell, extras, spans, cur, staple_vox,
            shell_vox=shell_vox, strip_new=strip_new,
        )
        if ok:
            print(f"    {label} air-span +{len(spans)} -> {cur}")
            continue

        near = _join_nearby_components(
            placements,
            extras,
            solid,
            staple_color=staple_color,
            plate_color=plate_color,
            staple_vox=staple_vox,
            max_dist=64,
        )
        extras, cur, ok = _keep_if_improves(
            shell, extras, near, cur, staple_vox,
            shell_vox=shell_vox, strip_new=strip_new,
        )
        if ok:
            print(f"    {label} nearby +{len(near)} -> {cur}")
            continue

        exhaust = _exhaustive_contact_plates(
            placements,
            extras,
            plate_color=plate_color,
            staple_vox=staple_vox,
        )
        extras, cur, ok = _keep_if_improves(
            shell, extras, exhaust, cur, staple_vox,
            shell_vox=shell_vox, strip_new=strip_new,
        )
        if ok:
            print(f"    {label} exhaust +{len(exhaust)} -> {cur}")
            continue

        # Staple bridges only while many fragments remain
        if cur > 6:
            mst = reconnect_sections_mst(
                placements,
                extras,
                solid,
                staple_color=staple_color,
                plate_color=plate_color,
                staple_vox=staple_vox,
                max_dist=48,
            )
            extras, cur, ok = _keep_if_improves(
                shell, extras, mst, cur, staple_vox,
                shell_vox=shell_vox, strip_new=strip_new,
            )
            if ok:
                print(f"    {label} mst +{len(mst)} -> {cur}")
                continue

            air = _staple_air_column_gaps(
                placements,
                extras,
                staple_color=staple_color,
                staple_vox=staple_vox,
                max_gap=8,
                solid=solid,
            )
            extras, cur, ok = _keep_if_improves(
                shell, extras, air, cur, staple_vox,
                shell_vox=shell_vox, strip_new=strip_new,
            )
            if ok:
                print(f"    {label} air-column +{len(air)} -> {cur}")
                more_top, _, _ = bridge_tops_with_plates(
                    placements,
                    extras,
                    plate_color=plate_color,
                    staple_vox=staple_vox,
                )
                if more_top:
                    extras, cur, _ = _keep_if_improves(
                        shell, extras, more_top, cur, staple_vox,
                        shell_vox=shell_vox, strip_new=strip_new,
                    )
                continue

            last = _staple_nearest_air_path(
                placements,
                extras,
                staple_color=staple_color,
                plate_color=plate_color,
                staple_vox=staple_vox,
                max_dist=32,
                solid=solid,
            )
            extras, cur, ok = _keep_if_improves(
                shell, extras, last, cur, staple_vox,
                shell_vox=shell_vox, strip_new=strip_new,
            )
            if ok:
                print(f"    {label} nearest-air +{len(last)} -> {cur}")
                continue

        # Spine/nuke only as last resort for severe fragmentation — they drop
        # plates and thrash section counts on hollow shells.
        if cur > 12:
            spine, new_extras = _reconnect_spine_clear_plates(
                placements,
                extras,
                staple_color=staple_color,
                staple_vox=staple_vox,
                max_gap=16,
                solid=solid,
            )
            if spine:
                nxt = check_connectivity(shell + new_extras).section_count
                if nxt < cur:
                    extras = new_extras
                    continue

            nuke, new_extras = _reconnect_spine_nuke_plates(
                placements,
                extras,
                staple_color=staple_color,
                staple_vox=staple_vox,
                max_gap=20,
                solid=solid,
            )
            if nuke:
                extras = new_extras
                for _fast in range(40):
                    cur2 = check_connectivity(shell + extras).section_count
                    if cur2 <= 1:
                        break
                    spans2 = _bridge_air_gaps_with_plates(
                        placements,
                        extras,
                        plate_color=plate_color,
                        staple_vox=staple_vox,
                        max_span=6,
                    )
                    extras, cur2, ok2 = _keep_if_improves(
                        shell, extras, spans2, cur2, staple_vox,
                        shell_vox=shell_vox, strip_new=strip_new,
                    )
                    if ok2:
                        continue
                    near2 = _join_nearby_components(
                        placements,
                        extras,
                        solid,
                        staple_color=staple_color,
                        plate_color=plate_color,
                        staple_vox=staple_vox,
                        max_dist=64,
                    )
                    extras, cur2, ok2 = _keep_if_improves(
                        shell, extras, near2, cur2, staple_vox,
                        shell_vox=shell_vox, strip_new=strip_new,
                    )
                    if ok2:
                        print(f"    post-nuke nearby +{len(near2)} -> {cur2}")
                        continue
                    mst2 = reconnect_sections_mst(
                        placements,
                        extras,
                        solid,
                        staple_color=staple_color,
                        plate_color=plate_color,
                        staple_vox=staple_vox,
                        max_dist=64,
                    )
                    extras, cur2, ok2 = _keep_if_improves(
                        shell, extras, mst2, cur2, staple_vox,
                        shell_vox=shell_vox, strip_new=strip_new,
                    )
                    if ok2:
                        print(f"    post-nuke mst +{len(mst2)} -> {cur2}")
                        continue
                    exhaust2 = _exhaustive_contact_plates(
                        placements,
                        extras,
                        plate_color=plate_color,
                        staple_vox=staple_vox,
                    )
                    extras, cur2, ok2 = _keep_if_improves(
                        shell, extras, exhaust2, cur2, staple_vox,
                        shell_vox=shell_vox, strip_new=strip_new,
                    )
                    if ok2:
                        continue
                    break
                continue

        # Last resort: MST even at low section counts
        mst = reconnect_sections_mst(
            placements,
            extras,
            solid,
            staple_color=staple_color,
            plate_color=plate_color,
            staple_vox=staple_vox,
            max_dist=64,
        )
        extras, cur, ok = _keep_if_improves(
            shell, extras, mst, cur, staple_vox,
            shell_vox=shell_vox, strip_new=strip_new,
        )
        if ok:
            print(f"    {label} last-mst +{len(mst)} -> {cur}")
            continue

        # Halo air/nearest even when few sections remain (equator floaters)
        air = _staple_air_column_gaps(
            placements,
            extras,
            staple_color=staple_color,
            staple_vox=staple_vox,
            max_gap=12,
            solid=solid,
        )
        extras, cur, ok = _keep_if_improves(
            shell, extras, air, cur, staple_vox,
            shell_vox=shell_vox, strip_new=strip_new,
        )
        if ok:
            print(f"    {label} last-air +{len(air)} -> {cur}")
            continue
        last = _staple_nearest_air_path(
            placements,
            extras,
            staple_color=staple_color,
            plate_color=plate_color,
            staple_vox=staple_vox,
            max_dist=40,
            solid=solid,
        )
        extras, cur, ok = _keep_if_improves(
            shell, extras, last, cur, staple_vox,
            shell_vox=shell_vox, strip_new=strip_new,
        )
        if ok:
            print(f"    {label} last-nearest +{len(last)} -> {cur}")
            continue
        break

    return extras


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
        placements, [], plate_color=plate_color, solid=solid
    )

    cavity: list[Brick] = []
    staples: list[Brick] = []
    staple_vox: set[tuple[int, int, int]] = set()
    sec_cavity = sec1
    sec_staples = sec1

    if solid is not None:
        extras = list(under)
        # One-cell UPWARD thicken — skip any cell that would collide
        shell_vox = _placement_voxels(placements)
        connect_vol = _connector_allowed_cells(solid, shell_vox)
        free = solid - shell_vox
        thicken_index = CollisionWorld(shell + under)
        thicken_bricks: list[Brick] = []
        for ix, iy, iz in shell_vox:
            above = (ix, iy + 1, iz)
            if above not in free:
                continue
            brick = _make_1x1_brick(staple_color, ix, iy + 1, iz)
            if thicken_index.collides(brick):
                continue
            thicken_index.add(brick)
            thicken_bricks.append(brick)
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
            solid=solid,
            cavity_only=False,
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
                solid=solid,
                cavity_only=False,
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
                placements,
                extras + staples,
                plate_color=plate_color,
                solid=solid,
            )
            if more_under and sec_under < sec_before_under:
                under.extend(more_under)
                extras = under + cavity
                improved = True
                cur = sec_under

            cur_after = check_connectivity(shell + extras + staples).section_count
            if cur_after > 1:
                # Plate-first: span/air plates, then nearby (plates+corners), then staples
                spans = _bridge_air_gaps_with_plates(
                    placements,
                    extras + staples,
                    plate_color=plate_color,
                    staple_vox=staple_vox,
                    max_span=6,
                )
                if spans:
                    cavity.extend(spans)
                    extras = under + cavity
                    improved = True
                    print(f"    air-span plates +{len(spans)}")
                else:
                    near = _join_nearby_components(
                        placements,
                        extras + staples,
                        connect_vol,
                        staple_color=staple_color,
                        plate_color=plate_color,
                        staple_vox=staple_vox,
                        max_dist=64,
                    )
                    if near:
                        staples.extend(near)
                        print(f"    nearby joins +{len(near)}")
                        improved = True
                    else:
                        air = _staple_air_column_gaps(
                            placements,
                            extras + staples,
                            staple_color=staple_color,
                            staple_vox=staple_vox,
                            max_gap=8,
                            solid=connect_vol,
                        )
                        if air:
                            staples.extend(air)
                            # Immediately try plates on the new staple tops
                            more_top, _, sec_top = bridge_tops_with_plates(
                                placements,
                                extras + staples,
                                plate_color=plate_color,
                                staple_vox=staple_vox,
                            )
                            if more_top and sec_top < cur_after:
                                cavity.extend(more_top)
                                extras = under + cavity
                            improved = True
                        else:
                            last = _staple_nearest_air_path(
                                placements,
                                extras + staples,
                                staple_color=staple_color,
                                plate_color=plate_color,
                                staple_vox=staple_vox,
                                max_dist=28,
                                solid=connect_vol,
                            )
                            if last:
                                staples.extend(last)
                                improved = True
                                print(f"    nearest-air +{len(last)}")

            new_sec = check_connectivity(shell + extras + staples).section_count
            if new_sec >= prev_sec:
                stagnant += 1
                if stagnant >= 5 or not improved:
                    break
            else:
                stagnant = 0
                prev_sec = new_sec

        # Plate-first reconnect; avoid air-column thrash when few sections remain.
        extras = under + cavity + staples
        extras = _reconnect_plate_first(
            placements,
            extras,
            connect_vol,
            plate_color=plate_color,
            staple_color=staple_color,
            staple_vox=staple_vox,
            label="final",
        )
        from catalog import get_part as _gp2

        under = []
        cavity = [b for b in extras if _gp2(b.part_id).kind == "plate"]
        staples = [
            b for b in extras if _gp2(b.part_id).kind not in ("plate", "tile")
        ]

    tiles, uncovered = cover_exterior_with_tiles(
        placements,
        shell + under + cavity + staples,
        tile_color=tile_color,
        solid=solid,
    )

    # Strip fused extras BEFORE gap-fill so connectors are not deleted by later packs
    cleaned, stripped = strip_colliding_extras(
        shell, under + cavity + staples + tiles
    )
    if stripped:
        print(f"    stripped {stripped} colliding extras")

    # Rebuild staple voxel set from whatever 1x1s survived the strip
    shell_vox = _placement_voxels(placements)
    staple_vox = set()
    for b in cleaned:
        cell = _1x1_brick_voxel(b)
        if cell is not None and cell not in shell_vox:
            staple_vox.add(cell)

    gap_plates: list[Brick] = []

    # Reconnect after strip — plate-first, nuke last
    if solid is not None:
        extras = list(cleaned)
        extras = _reconnect_plate_first(
            placements,
            extras,
            connect_vol,
            plate_color=plate_color,
            staple_color=staple_color,
            staple_vox=staple_vox,
            label="post-strip",
            strip_new=True,
            shell_vox=shell_vox,
        )
        cleaned = extras

    # Cosmetic gap-fill only after reconnect (never sacrifice connectivity)
    if check_connectivity(shell + cleaned).section_count <= 1:
        gap_plates = pack_open_stud_gaps(
            placements,
            shell + cleaned,
            plate_color=plate_color,
            solid=solid,
            staple_vox=staple_vox,
        )
        if gap_plates:
            cleaned = cleaned + gap_plates
            print(f"    gap-fill strips +{len(gap_plates)}")

    all_bricks = shell + cleaned
    # One more strip in case reconnect added overlaps
    cleaned2, stripped2 = strip_colliding_extras(shell, cleaned)
    if stripped2:
        print(f"    stripped {stripped2} post-reconnect collisions")
        cleaned = cleaned2
        all_bricks = shell + cleaned

    # Prune 1x1 staples that are not required for single-section connectivity
    cleaned, pruned = _prune_redundant_staples(shell, cleaned)
    if pruned:
        print(f"    pruned {pruned} redundant staples")
        all_bricks = shell + cleaned

    cleaned, pruned_col = _prune_colliding_plates(shell, cleaned)
    if pruned_col:
        print(f"    pruned {pruned_col} colliding plates/tiles")
        all_bricks = shell + cleaned

    # Merge adjacent 1x1 staples into longest 1xN for stronger clutch (1 section only)
    if check_connectivity(shell + cleaned).section_count == 1:
        cleaned, n_merged = _bond_strengthen_pass(
            shell, cleaned, staple_color=staple_color
        )
        if n_merged:
            print(f"    bond-merge {n_merged} longer staple bricks")
            all_bricks = shell + cleaned

        # If weak 1-stud joins still dominate, try one inward hollow thicken ring
        cleaned, n_thick = _try_inward_hollow_thicken(
            shell,
            cleaned,
            solid=solid,
            shell_vox=shell_vox if solid is not None else set(),
            staple_color=staple_color,
            staple_vox=staple_vox,
        )
        if n_thick:
            print(f"    hollow thicken +{n_thick} (2-stud wall attempt)")
            all_bricks = shell + cleaned
            # Re-bond after thicken
            cleaned, n_merged2 = _bond_strengthen_pass(
                shell, cleaned, staple_color=staple_color
            )
            if n_merged2:
                print(f"    bond-merge after thicken {n_merged2}")
                all_bricks = shell + cleaned

    # Drop any remaining exterior 1x1s outside the solid ball
    if solid is not None:
        cleaned, n_out = _filter_exterior_staples(
            shell, cleaned, solid, shell_vox
        )
        if n_out:
            print(f"    dropped {n_out} exterior staples outside solid")
            all_bricks = shell + cleaned

    # Soft clutch-strength stats (not a PASS gate)
    strength = clutch_strength(shell + cleaned)
    all_bricks = shell + cleaned
    sec2 = check_connectivity(all_bricks).section_count
    cols = count_collisions(all_bricks)

    # Recount staples/plates/tiles from cleaned for accurate stats
    from catalog import get_part as _gp_stats

    n_staples = sum(
        1 for b in cleaned if _gp_stats(b.part_id).kind not in ("plate", "tile")
    )
    n_plates = sum(1 for b in cleaned if _gp_stats(b.part_id).kind == "plate")
    n_tiles = sum(1 for b in cleaned if _gp_stats(b.part_id).kind == "tile")

    stats = {
        "sections_before": sec0,
        "sections_after_under": sec1,
        "sections_after_cavity": sec_cavity,
        "sections_after_staples": sec_staples,
        "sections_final": sec2,
        "under_plates": len(under),
        "cavity_plates": len(cavity),
        "staples": n_staples,
        "plates": n_plates,
        "tiles": n_tiles,
        "uncovered_studs": uncovered,
        "collisions": cols,
        "gap_fill_plates": len(gap_plates),
        "stripped_collisions": stripped + stripped2,
        "pruned_staples": pruned,
        "weak_edges": strength.weak_edges,
        "clutch_edges": strength.edge_count,
        "mean_overlap": strength.mean_overlap,
    }
    return all_bricks, stats


def _plated_top_cells(bricks: list[Brick]) -> set[tuple[int, int]]:
    """Return (ix, iz) stud cells already covered by a plate/tile on some layer."""
    from catalog import get_part

    covered: set[tuple[int, int]] = set()
    for b in bricks:
        spec = get_part(b.part_id)
        if spec.kind not in ("plate", "tile"):
            continue
        w, d = spec.width, spec.depth
        yaw90 = abs(b.a) < 0.1 and abs(b.g) > 0.9
        if yaw90:
            w, d = d, w
        cx = b.x / STUD
        cz = b.z / STUD
        ix0 = int(round(cx - w / 2.0))
        iz0 = int(round(cz - d / 2.0))
        for x in range(ix0, ix0 + w):
            for z in range(iz0, iz0 + d):
                covered.add((x, z))
    return covered


def reconnect_sections_mst(
    placements: list[Placement],
    existing: list[Brick],
    solid: SolidCells,
    *,
    staple_color: int,
    plate_color: int,
    staple_vox: set[tuple[int, int, int]],
    max_dist: int = 32,
) -> list[Brick]:
    """Kruskal-style collision-safe bridges until one clutch section (or stuck)."""
    shell = placements_to_bricks(placements)
    world = list(shell) + list(existing)
    before = check_connectivity(world).section_count
    if before <= 1:
        return []

    occupied = _placement_voxels(placements)
    free_solid = solid - occupied - staple_vox
    index = CollisionWorld(world)
    added: list[Brick] = []

    def refresh_sections() -> tuple[
        dict[tuple[int, int, int], int], dict[int, list[tuple[int, int, int]]], int
    ]:
        report = check_connectivity(world)
        vsec: dict[tuple[int, int, int], int] = {}
        for i, p in enumerate(placements):
            for x, z in _footprint_cells(p):
                vsec[(x, p.iy, z)] = report.component_of[i]
        for i, b in enumerate(world):
            cell = _1x1_brick_voxel(b)
            if cell is not None and cell in staple_vox:
                vsec[cell] = report.component_of[i]
        by: dict[int, list[tuple[int, int, int]]] = {}
        for cell, sec in vsec.items():
            by.setdefault(sec, []).append(cell)
        return vsec, by, report.section_count

    def try_add_fill(
        fill: list[tuple[int, int, int]], a: tuple[int, int, int], b: tuple[int, int, int]
    ) -> bool:
        nonlocal before
        occ = occupied | staple_vox
        if any(c in occ for c in fill):
            return False
        snap_w = len(world)
        snap_i = len(index.bricks)
        snap_a = len(added)
        batch: list[Brick] = []
        for fx, fy, fz in fill:
            brick = _make_1x1_brick(staple_color, fx, fy, fz)
            if index.collides_flat(brick):
                while len(world) > snap_w:
                    world.pop()
                index.truncate(snap_i)
                for cx, cy, cz in fill[: len(batch)]:
                    staple_vox.discard((cx, cy, cz))
                return False
            world.append(brick)
            index.add(brick)
            batch.append(brick)
            staple_vox.add((fx, fy, fz))
        chain = [a] + fill + [b]
        for i in range(len(chain) - 1):
            plate = _plate_1x2_on_pair(
                chain[i], chain[i + 1], plate_color, index=index
            )
            if plate is None:
                continue
            world.append(plate)
            index.add(plate)
            batch.append(plate)
        after = check_connectivity(world).section_count
        if after < before:
            added.extend(batch)
            before = after
            print(f"    mst bridge +{len(fill)} -> {after} sections")
            return True
        while len(world) > snap_w:
            world.pop()
        index.truncate(snap_i)
        for fx, fy, fz in fill:
            staple_vox.discard((fx, fy, fz))
        del added[snap_a:]
        return False

    def air_l_path(
        a: tuple[int, int, int], b: tuple[int, int, int]
    ) -> list[tuple[int, int, int]]:
        occ = occupied | staple_vox
        allowed = free_solid

        def one(order: str) -> list[tuple[int, int, int]]:
            cells: list[tuple[int, int, int]] = []
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
                        return cells
                    if cell in occ or cell not in allowed:
                        return []
                    cells.append(cell)
            return cells

        return one("yxz") or one("xyz") or one("xzy") or one("zyx") or one("zxy")

    def air_bfs_path(
        a: tuple[int, int, int], b: tuple[int, int, int]
    ) -> list[tuple[int, int, int]]:
        """Short path through free solid only (no exterior air)."""
        occ = occupied | staple_vox
        allowed = free_solid
        if a == b:
            return []
        neigh = (
            (1, 0, 0),
            (-1, 0, 0),
            (0, 1, 0),
            (0, -1, 0),
            (0, 0, 1),
            (0, 0, -1),
        )
        q: deque[tuple[tuple[int, int, int], int]] = deque()
        parent: dict[tuple[int, int, int], tuple[int, int, int] | None] = {}
        for dx, dy, dz in neigh:
            n = (a[0] + dx, a[1] + dy, a[2] + dz)
            if n == b:
                return []
            if n in occ or n not in allowed:
                continue
            parent[n] = None
            q.append((n, 1))
        while q:
            cur, dist = q.popleft()
            for dx, dy, dz in neigh:
                n = (cur[0] + dx, cur[1] + dy, cur[2] + dz)
                if n == b:
                    path = [cur]
                    p = parent[cur]
                    while p is not None:
                        path.append(p)
                        p = parent[p]
                    path.reverse()
                    return path
                if n in occ or n not in allowed or n in parent or n == a:
                    continue
                if dist >= min(max_dist, 24) or len(parent) >= 2500:
                    continue
                parent[n] = cur
                q.append((n, dist + 1))
        return []

    failed: set[int] = set()
    for _round in range(200):
        vsec, by_sec, nsec = refresh_sections()
        before = nsec
        if nsec <= 1:
            break
        largest = max(by_sec, key=lambda s: len(by_sec[s]))
        goals = by_sec[largest]
        candidates = [s for s in by_sec if s != largest and s not in failed]
        if not candidates:
            print(f"    mst stuck at {before} sections")
            break
        small = min(candidates, key=lambda s: len(by_sec[s]))
        members = by_sec[small]

        pairs: list[tuple[int, tuple[int, int, int], tuple[int, int, int]]] = []
        step_g = max(1, len(goals) // 60)
        step_m = max(1, len(members) // 30)
        for a in members[::step_m]:
            for b in goals[::step_g]:
                d = abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
                if 0 < d <= max_dist:
                    pairs.append((d, a, b))
        pairs.sort(key=lambda t: t[0])
        if not pairs:
            failed.add(small)
            continue

        made = False
        for d, a, b in pairs[:8]:
            if d == 1 and a[1] == b[1]:
                plate = _plate_1x2_on_pair(a, b, plate_color, index=index)
                if plate is not None:
                    world.append(plate)
                    index.add(plate)
                    after = check_connectivity(world).section_count
                    if after < before:
                        added.append(plate)
                        before = after
                        print(f"    mst plate -> {after} sections")
                        made = True
                        break
                    world.pop()
                    index.truncate(len(index.bricks) - 1)

            fill, aa, bb = _bfs_fill_path([a], [b], free_solid, max_dist=max_dist)
            if not fill or aa is None or bb is None:
                fill = air_l_path(a, b)
                if not fill and d <= 24:
                    fill = air_bfs_path(a, b)
                aa, bb = a, b
            if fill and try_add_fill(fill, aa, bb):
                free_solid -= set(fill)
                made = True
                break

        if not made:
            failed.add(small)
            continue
        failed.clear()
    return added


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
    already = _plated_top_cells(existing)
    free_by_layer: dict[int, dict[tuple[int, int], int]] = {}
    for iy, cells in occ.items():
        above = occ.get(iy + 1, set()) | {
            (x, z) for x, y, z in staples if y == iy + 1
        }
        ext = exterior.get(iy, set())
        free = {
            (x, z): 0
            for x, z in cells
            if (x, z) not in above
            and (x, z) not in ext
            and (x, z) not in already
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
