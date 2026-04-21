"""Wallpaper-group tessellation.

v1 implements p3: three motifs per lattice point, each rotated 0°/120°/240°
around the motif's ``anchor`` vertex (which lands AT the lattice point).
For a properly p3-designed motif (e.g. an Escher lizard), this produces
true Escher-style interlock with zero gaps and zero overlap.

For an *un*designed motif the same algorithm produces overlap (because the
motif edges don't match their 120° rotations) — it's the user's job to
supply a p3 tile and to set the anchor to one of the motif's 3-fold
rotation centres (a specific vertex on the outline, not the centroid).

Algorithm:
  * Hex lattice, basis a=(L,0), b=(L/2, L·√3/2) in motif-local units.
  * At each lattice point, place 3 motif copies rotated 0°/120°/240°
    about ``anchor``. The anchor of each copy lands at the lattice point.
  * L defaults to max(motif bbox); users tune via ``lattice_scale``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from shapely.geometry import Polygon, box

Group = Literal["p1", "p2", "p3", "p4", "p6"]


@dataclass
class Transform2D:
    scale: float
    rotation_deg: float
    offset: tuple[float, float]


@dataclass
class ClipBounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float


@dataclass
class PlacedTile:
    tile_id: str
    polygon: list[tuple[float, float]]
    centroid: tuple[float, float]
    area_mm2: float
    rotation_deg: float


def tessellate(
    polygon: list[tuple[float, float]],
    group: Group,
    global_transform: Transform2D,
    clip_bounds: ClipBounds,
    lattice_scale: float = 1.0,
    anchor: tuple[float, float] = (0.0, 0.0),
    pivots: list[tuple[float, float]] | None = None,
) -> list[PlacedTile]:
    if group == "p3":
        return _tessellate_p3(
            polygon, global_transform, clip_bounds, lattice_scale, anchor, pivots or []
        )
    raise NotImplementedError(f"group {group} not implemented yet")


# ---------- p3 ----------


def _tessellate_p3(
    motif: list[tuple[float, float]],
    gt: Transform2D,
    clip: ClipBounds,
    lattice_scale: float,
    anchor: tuple[float, float],
    pivots: list[tuple[float, float]],
) -> list[PlacedTile]:
    # Derive lattice basis vectors from the pivot triangle. For a same-orbit p3
    # tile (3 pivots forming an equilateral triangle, like regular hex or a
    # typical Escher lizard), the primitive lattice has |a| = |b| = 3·|r|
    # where r is the vector from the pivot-triangle centroid to pivot[0].
    # Orientation of a follows r exactly (matches the tile's pivot-triangle
    # rotation in the plane); b is rotated 60° CCW from a. With no pivots we
    # fall back to an axis-aligned bbox-based lattice.
    if len(pivots) >= 3:
        p0, p1, p2 = pivots[:3]
        cx_piv = (p0[0] + p1[0] + p2[0]) / 3.0
        cy_piv = (p0[1] + p1[1] + p2[1]) / 3.0
        rx = p0[0] - cx_piv
        ry = p0[1] - cy_piv
        scale_factor = 3.0 * max(lattice_scale, 0.01)
        ax = rx * scale_factor
        ay = ry * scale_factor
        bx = ax * 0.5 - ay * (math.sqrt(3) / 2)
        by = ax * (math.sqrt(3) / 2) + ay * 0.5
        lattice_const = math.hypot(ax, ay)
    elif len(pivots) >= 2:
        px0, py0 = pivots[0]
        px1, py1 = pivots[1]
        pivot_dist = math.hypot(px1 - px0, py1 - py0)
        lattice_const = pivot_dist * math.sqrt(3) * max(lattice_scale, 0.01)
        ax, ay = lattice_const, 0.0
        bx, by = lattice_const * 0.5, lattice_const * math.sqrt(3) / 2
    else:
        arr = np.asarray(motif, dtype=float)
        bbox_w = float(arr[:, 0].max() - arr[:, 0].min())
        bbox_h = float(arr[:, 1].max() - arr[:, 1].min())
        motif_span = max(bbox_w, bbox_h)
        lattice_const = motif_span * max(lattice_scale, 0.01)
        ax, ay = lattice_const, 0.0
        bx, by = lattice_const * 0.5, lattice_const * math.sqrt(3) / 2

    # Compute how many cells we need by mapping the (scaled, transformed)
    # clip bounds back into motif-local space.
    s = gt.scale
    inv_scale = 1.0 / s if s != 0 else 1.0
    # We iterate a generous (i,j) range then prune with the clip.
    half_diag = (
        math.hypot(clip.max_x - clip.min_x, clip.max_y - clip.min_y) * 0.5 * inv_scale
    )
    n = max(4, int(math.ceil(half_diag / lattice_const)) + 2)

    clip_poly = box(clip.min_x, clip.min_y, clip.max_x, clip.max_y)
    rot_global = math.radians(gt.rotation_deg)
    cos_g = math.cos(rot_global)
    sin_g = math.sin(rot_global)
    ax_anchor, ay_anchor = anchor

    placed: list[PlacedTile] = []
    tile_counter = 0

    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            cx = i * ax + j * bx
            cy = i * ay + j * by
            # Three motifs per lattice point, rotated 0/120/240 about the
            # motif's anchor (which lands AT the lattice point).
            for k in range(3):
                theta = math.radians(120 * k)
                cos_l = math.cos(theta)
                sin_l = math.sin(theta)
                pts: list[tuple[float, float]] = []
                for x, y in motif:
                    # Move motif so the anchor sits at origin.
                    tx = x - ax_anchor
                    ty = y - ay_anchor
                    # Rotate about the anchor (now at origin).
                    rx = tx * cos_l - ty * sin_l
                    ry = tx * sin_l + ty * cos_l
                    # Place anchor at the lattice point.
                    lx = rx + cx
                    ly = ry + cy
                    # Apply global transform: scale, rotate, offset.
                    sx = lx * s
                    sy = ly * s
                    gx = sx * cos_g - sy * sin_g + gt.offset[0]
                    gy = sx * sin_g + sy * cos_g + gt.offset[1]
                    pts.append((gx, gy))

                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_empty:
                    continue
                if not poly.intersects(clip_poly):
                    continue

                centroid = poly.centroid
                placed.append(
                    PlacedTile(
                        tile_id=f"t-{tile_counter:04d}",
                        polygon=list(poly.exterior.coords)[:-1],
                        centroid=(float(centroid.x), float(centroid.y)),
                        area_mm2=float(poly.area),
                        rotation_deg=(gt.rotation_deg + 120 * k) % 360,
                    )
                )
                tile_counter += 1

    return placed
