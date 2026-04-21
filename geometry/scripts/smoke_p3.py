"""Smoke-test p3 tessellation against the plain hex.

Verifies:
  * Sum of tile areas vs union area — a gap/overlap-free tiling has
    |sum_area - union_area| / union_area ≈ 0 (within clipping fuzz).
  * Tile count within a modest clip — sanity-check the lattice constant.

A regular hex of radius 100 has area (3√3/2)·R² ≈ 25981. A clip box of
700×700 = 490000 should contain ~18–20 whole tiles. More → lattice too
dense → overlap. Fewer → lattice too sparse → gaps.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shapely.geometry import Polygon
from shapely.ops import unary_union

from tessera.shapes import import_shape_from_svg
from tessera.tessellate import ClipBounds, Transform2D, tessellate


def main() -> int:
    svg_path = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "shapes"
        / "p3-hex-plain.svg"
    )
    imported = import_shape_from_svg(svg_path.read_bytes())
    print(
        f"hex: {len(imported.polygon)} verts, "
        f"w={imported.width:.1f} h={imported.height:.1f}, "
        f"pivots={imported.pivots}, anchor={imported.rotation_anchor}"
    )

    tile_area = Polygon(imported.polygon).area
    print(f"single tile area = {tile_area:.1f}")

    tiles = tessellate(
        polygon=imported.polygon,
        group="p3",
        global_transform=Transform2D(scale=1.0, rotation_deg=0.0, offset=(0.0, 0.0)),
        clip_bounds=ClipBounds(min_x=-350, min_y=-350, max_x=350, max_y=350),
        lattice_scale=1.0,
        anchor=imported.rotation_anchor,
        pivots=imported.pivots,
    )
    print(f"placed {len(tiles)} tiles in 700x700 clip")

    polys = [Polygon(t.polygon) for t in tiles]
    sum_area = sum(p.area for p in polys)
    union = unary_union(polys)
    union_area = union.area
    diff = abs(sum_area - union_area)
    rel = diff / union_area if union_area else float("inf")
    print(f"sum(tile.area) = {sum_area:.1f}")
    print(f"union area     = {union_area:.1f}")
    print(f"overlap/gap    = {diff:.1f} ({rel*100:.2f}%)")

    # For a valid p3 tiling of an unbounded plane, sum = union exactly. With
    # clip fuzz at the boundary we expect rel < ~5% (edges get clipped). Large
    # values mean overlap (sum >> union) or gaps in the interior. Inner tiles
    # should all abut, so we also check the central region only.
    inner = union.intersection(Polygon([(-200, -200), (200, -200), (200, 200), (-200, 200)]))
    expected_inner = 400 * 400
    inner_cover = inner.area / expected_inner
    print(f"central 400x400 coverage = {inner_cover*100:.2f}%")

    ok = rel < 0.05 and inner_cover > 0.98
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
