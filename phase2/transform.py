"""
Phase 2, Step 1 — LDraw transforms for the scene graph.

Blueprint anchor: Phase 2 (Scene Graph & Connection Engine).

Spatial math (LDraw):
  - Right-handed, -Y is up.
  - A transform is rotation R (3x3) + translation t (3).
  - Child world pose:  R_w = R_parent @ R_local
                       t_w = R_parent @ t_local + t_parent
  - Line-type-1 matrix layout (a..i):
        / a d g \\
        | b e h |
        \\ c f i /
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transform:
    """Rigid transform: rotation (LDraw a..i) + translation (LDU)."""

    # Translation
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    # Rotation (LDraw a b c d e f g h i)
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0
    e: float = 1.0
    f: float = 0.0
    g: float = 0.0
    h: float = 0.0
    i: float = 1.0

    @staticmethod
    def identity() -> Transform:
        return Transform()

    @staticmethod
    def translation(x: float, y: float, z: float) -> Transform:
        return Transform(x=x, y=y, z=z)

    @staticmethod
    def yaw_180(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Transform:
        """180° about Y, then translate. Flips facing for slopes."""
        return Transform(x=x, y=y, z=z, a=-1.0, e=1.0, i=-1.0)

    def rotate_point(self, px: float, py: float, pz: float) -> tuple[float, float, float]:
        """Apply this transform's rotation to a point (no translation)."""
        # column vector p' = R @ p with R = [[a,d,g],[b,e,h],[c,f,i]]
        rx = self.a * px + self.d * py + self.g * pz
        ry = self.b * px + self.e * py + self.h * pz
        rz = self.c * px + self.f * py + self.i * pz
        return rx, ry, rz

    def apply(self, px: float, py: float, pz: float) -> tuple[float, float, float]:
        """Rotate then translate a point."""
        rx, ry, rz = self.rotate_point(px, py, pz)
        return rx + self.x, ry + self.y, rz + self.z

    def compose(self, local: Transform) -> Transform:
        """
        Parent ∘ local → world.

          R_w = R_parent @ R_local
          t_w = R_parent @ t_local + t_parent
        """
        # R_parent @ t_local
        lx, ly, lz = self.rotate_point(local.x, local.y, local.z)
        tx, ty, tz = lx + self.x, ly + self.y, lz + self.z

        # R_parent @ R_local  (both in LDraw a..i layout)
        # Parent columns are (a,b,c), (d,e,f), (g,h,i)
        pa, pb, pc = self.a, self.b, self.c
        pd, pe, pf = self.d, self.e, self.f
        pg, ph, pi = self.g, self.h, self.i

        la, lb, lc = local.a, local.b, local.c
        ld, le, lf = local.d, local.e, local.f
        lg, lh, li = local.g, local.h, local.i

        # Column 0 of result = R_p @ col0(R_l)
        ra = pa * la + pd * lb + pg * lc
        rb = pb * la + pe * lb + ph * lc
        rc = pc * la + pf * lb + pi * lc
        # Column 1
        rd = pa * ld + pd * le + pg * lf
        re = pb * ld + pe * le + ph * lf
        rf = pc * ld + pf * le + pi * lf
        # Column 2
        rg = pa * lg + pd * lh + pg * li
        rh = pb * lg + pe * lh + ph * li
        ri = pc * lg + pf * lh + pi * li

        return Transform(
            x=tx, y=ty, z=tz,
            a=ra, b=rb, c=rc,
            d=rd, e=re, f=rf,
            g=rg, h=rh, i=ri,
        )
