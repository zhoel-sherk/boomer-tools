"""2D similarity transform: map PnP plane (mm) into Gerber/scene plane (mm)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def __sub__(self, o: Vec2) -> Vec2:
        return Vec2(self.x - o.x, self.y - o.y)

    def __add__(self, o: Vec2) -> Vec2:
        return Vec2(self.x + o.x, self.y + o.y)

    def dot(self, o: Vec2) -> float:
        return self.x * o.x + self.y * o.y

    def cross_z(self, o: Vec2) -> float:
        return self.x * o.y - self.y * o.x

    def length(self) -> float:
        return math.hypot(self.x, self.y)


@dataclass(frozen=True)
class Similarity2D:
    """g = s * R(theta) * p + t  (R rotates CCW in standard math frame, +x right +y up)."""

    scale: float
    cos_t: float
    sin_t: float
    tx: float
    ty: float

    @staticmethod
    def identity() -> Similarity2D:
        return Similarity2D(1.0, 1.0, 0.0, 0.0, 0.0)

    def apply(self, px: float, py: float) -> tuple[float, float]:
        rx = self.cos_t * px - self.sin_t * py
        ry = self.sin_t * px + self.cos_t * py
        gx = self.scale * rx + self.tx
        gy = self.scale * ry + self.ty
        return gx, gy

    def compose(self, inner: Similarity2D) -> Similarity2D:
        """self ∘ inner: apply inner first, then self (same convention as matrix multiply)."""
        # M = s * [[c, -s], [s, c]]; compose: M_o @ M_i and t = M_o @ t_i + t_o
        a11 = self.scale * (self.cos_t * inner.cos_t - self.sin_t * inner.sin_t)
        a12 = self.scale * (-(self.cos_t * inner.sin_t + self.sin_t * inner.cos_t))
        a21 = self.scale * (self.sin_t * inner.cos_t + self.cos_t * inner.sin_t)
        a22 = self.scale * (-self.sin_t * inner.sin_t + self.cos_t * inner.cos_t)
        s_out = math.hypot(a11, a21)
        if s_out < 1e-12:
            return Similarity2D.identity()
        c_out = a11 / s_out
        sn_out = a21 / s_out
        tix, tiy = inner.tx, inner.ty
        tx_out = self.scale * (self.cos_t * tix - self.sin_t * tiy) + self.tx
        ty_out = self.scale * (self.sin_t * tix + self.cos_t * tiy) + self.ty
        return Similarity2D(s_out, c_out, sn_out, tx_out, ty_out)


def similarity_from_two_point_pairs(
    p1: tuple[float, float],
    p2: tuple[float, float],
    g1: tuple[float, float],
    g2: tuple[float, float],
    eps: float = 1e-9,
) -> Similarity2D:
    """
    Find similarity T such that T(pi) ≈ gi (least squares exact for two pairs if not degenerate).

    Uses vector from p1->p2 vs g1->g2 for rotation+scale, then translation.
    """
    px1, py1 = p1
    px2, py2 = p2
    gx1, gy1 = g1
    gx2, gy2 = g2
    vp = Vec2(px2 - px1, py2 - py1)
    vg = Vec2(gx2 - gx1, gy2 - gy1)
    lp = vp.length()
    lg = vg.length()
    if lp < eps or lg < eps:
        return Similarity2D.identity()
    s = lg / lp
    ap = math.atan2(vp.y, vp.x)
    ag = math.atan2(vg.y, vg.x)
    theta = ag - ap
    c = math.cos(theta)
    sn = math.sin(theta)
    rx = c * px1 - sn * py1
    ry = sn * px1 + c * py1
    tx = gx1 - s * rx
    ty = gy1 - s * ry
    return Similarity2D(s, c, sn, tx, ty)
