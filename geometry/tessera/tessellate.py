"""Wallpaper-group tessellation.

v1 specializes the p3 group (3-fold rotational symmetry, no reflection) —
the group Escher's lizard lives in. Other wallpaper groups (p1, p2, p4, p6)
will be generalized in later milestones.

Algorithm (p3):
  * Three lizards per hex vertex, rotated 0°, 120°, 240° about that vertex.
  * Hex lattice with basis vectors a=(L,0), b=(L/2, L*sqrt(3)/2) in native
    motif units. L is the lattice constant — for a correctly-designed Escher
    motif, L equals the motif's circumscribing-hexagon edge length.

We don't *solve* for L here — the user drives it via
``tiling.globalTransform.scale``. For an Escher lizard polygon exported at
"canonical" size, scale = 1 should already tile cleanly.
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
) -> list[PlacedTile]:
    if group == "p3":
        return _tessellate_p3(polygon, global_transform, clip_bounds)
    raise NotImplementedError(f"group {group} not implemented yet")


# ---------- p3 ----------


def _tessellate_p3(
    motif: list[tuple[float, float]],
    gt: Transform2D,
    clip: ClipBounds,
) -> list[PlacedTile]:
    # Derive a lattice constant from the motif's bounding box. This picks a
    # reasonable default for a motif whose circumscribing hexagon has edge
    # ~= bounding-box half-width. Users tune ``scale`` until it tessellates.
    arr = np.asarray(motif, dtype=float)
    bbox_w = float(arr[:, 0].max() - arr[:, 0].min())
    bbox_h = float(arr[:, 1].max() - arr[:, 1].min())
    motif_span = max(bbox_w, bbox_h) * 0.5
    lattice_const = motif_span

    # Hex lattice basis in motif-local units.
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

    placed: list[PlacedTile] = []
    tile_counter = 0

    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            cx = i * ax + j * bx
            cy = i * ay + j * by
            # Three motifs per lattice point, rotated 0/120/240 about (cx,cy).
            for k in range(3):
                theta = math.radians(120 * k)
                cos_l = math.cos(theta)
                sin_l = math.sin(theta)
                pts: list[tuple[float, float]] = []
                for x, y in motif:
                    # Rotate motif about its own origin by (theta).
                    rx = x * cos_l - y * sin_l
                    ry = x * sin_l + y * cos_l
                    # Translate to lattice point.
                    lx = rx + cx
                    ly = ry + cy
                    # Apply global transform: scale, then rotate, then offset.
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
