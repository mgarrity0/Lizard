"""Check whether the bbox-fallback tessellation of lizard.svg is clean.

Does NOT rely on pivot metadata — uses whatever the tessellator derives
(anchor = (0,0) = centroid, lattice_const = max(bbox)).

Clean tiling: sum(tile_area) ≈ union(tile_area), i.e. gap/overlap ≈ 0.
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
    src = (Path(__file__).resolve().parents[2] /
           "assets" / "shapes" / "lizard.svg")
    imported = import_shape_from_svg(src.read_bytes())
    print(f"loaded: {len(imported.polygon)} verts, "
          f"{imported.width:.0f}×{imported.height:.0f}, "
          f"pivots={len(imported.pivots)}")
    print(f"anchor={imported.rotation_anchor}")

    tile_area = Polygon(imported.polygon).area
    print(f"single tile area = {tile_area:.1f}")

    # Call tessellate without pivots — forces bbox fallback.
    tiles = tessellate(
        polygon=imported.polygon,
        group="p3",
        global_transform=Transform2D(scale=1.0, rotation_deg=0.0,
                                     offset=(0.0, 0.0)),
        clip_bounds=ClipBounds(min_x=-1500, min_y=-1500,
                               max_x=1500, max_y=1500),
        lattice_scale=1.0,
        anchor=imported.rotation_anchor,
        pivots=[],  # force bbox fallback
    )
    print(f"placed {len(tiles)} tiles in 3000x3000 clip (bbox fallback)")

    polys = [Polygon(t.polygon) for t in tiles]
    polys = [p for p in polys if p.is_valid and not p.is_empty]
    sum_area = sum(p.area for p in polys)
    union = unary_union(polys)
    ua = union.area
    rel = abs(sum_area - ua) / ua if ua else float("inf")
    print(f"sum(tile.area) = {sum_area:.1f}")
    print(f"union area     = {ua:.1f}")
    print(f"gap/overlap    = {rel*100:.2f}%  "
          f"({'overlap' if sum_area > ua else 'gaps'})")

    return 0 if rel < 0.02 else 1


if __name__ == "__main__":
    raise SystemExit(main())
