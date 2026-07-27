"""
Phase 3 — Triangle mesh helpers (generate + load OBJ).

Blueprint anchor: Phase 3 Naive Mesh-to-Brick Voxelizer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Mesh:
    """Triangle soup in arbitrary units (we treat them as LDU unless scaled)."""

    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    # Each face = 3 indices into vertices
    faces: list[tuple[int, int, int]] = field(default_factory=list)

    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        if not self.vertices:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        zs = [v[2] for v in self.vertices]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def scale(self, s: float) -> Mesh:
        self.vertices = [(x * s, y * s, z * s) for x, y, z in self.vertices]
        return self

    def translate(self, dx: float, dy: float, dz: float) -> Mesh:
        self.vertices = [(x + dx, y + dy, z + dz) for x, y, z in self.vertices]
        return self


def make_box(xmin: float, ymin: float, zmin: float,
             xmax: float, ymax: float, zmax: float) -> Mesh:
    """Axis-aligned box as 12 triangles (outward CCW when +Y is up in mesh space)."""
    # Mesh space here uses +Y up (common OBJ). We convert to LDraw in voxelize.
    v = [
        (xmin, ymin, zmin),  # 0
        (xmax, ymin, zmin),  # 1
        (xmax, ymax, zmin),  # 2
        (xmin, ymax, zmin),  # 3
        (xmin, ymin, zmax),  # 4
        (xmax, ymin, zmax),  # 5
        (xmax, ymax, zmax),  # 6
        (xmin, ymax, zmax),  # 7
    ]
    # faces (CCW from outside)
    f = [
        (0, 1, 2), (0, 2, 3),  # -Z
        (5, 4, 7), (5, 7, 6),  # +Z
        (4, 0, 3), (4, 3, 7),  # -X
        (1, 5, 6), (1, 6, 2),  # +X
        (3, 2, 6), (3, 6, 7),  # +Y
        (4, 5, 1), (4, 1, 0),  # -Y
    ]
    return Mesh(vertices=v, faces=f)


def write_obj(mesh: Mesh, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Phase 3 generated mesh", "o mesh"]
    for x, y, z in mesh.vertices:
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
    for a, b, c in mesh.faces:
        lines.append(f"f {a + 1} {b + 1} {c + 1}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_obj(path: Path) -> Mesh:
    """Minimal OBJ loader (v + triangular f only)."""
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "v" and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "f" and len(parts) >= 4:
            idxs = []
            for p in parts[1:]:
                idxs.append(int(p.split("/")[0]) - 1)
            # triangulate fan if needed
            for i in range(1, len(idxs) - 1):
                faces.append((idxs[0], idxs[i], idxs[i + 1]))
    return Mesh(vertices=vertices, faces=faces)


def make_hammer() -> Mesh:
    """Simple hammer: handle box + head box (mesh +Y up)."""
    handle = make_box(-4, 0, -4, 4, 80, 4)
    head = make_box(-28, 64, -10, 28, 88, 10)
    # Merge into one mesh
    verts = list(handle.vertices) + list(head.vertices)
    off = len(handle.vertices)
    faces = list(handle.faces) + [
        (a + off, b + off, c + off) for a, b, c in head.faces
    ]
    return Mesh(vertices=verts, faces=faces)
