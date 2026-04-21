"""End-to-end verify: import lizard.svg, tessellate using its embedded
data-p3-pivots, measure gap/overlap. This mirrors what the Tauri app does
on import, so a PASS here means the UI will see a clean tiling."""
from __future__ import annotations

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
          f"{imported.width:.0f}x{imported.height:.0f}, "
          f"pivots={len(imported.pivots)}")
    for p in imported.pivots:
        print(f"  pivot (centred): {p}")
    print(f"anchor: {imported.rotation_anchor}")

    tile_area = Polygon(imported.polygon).area
    print(f"single tile area = {tile_area:.1f}")

    tiles = tessellate(
        polygon=imported.polygon, group="p3",
        global_transform=Transform2D(scale=1.0, rotation_deg=0.0,
                                     offset=(0.0, 0.0)),
        clip_bounds=ClipBounds(min_x=-1500, min_y=-1500,
                               max_x=1500, max_y=1500),
        lattice_scale=1.0,
        anchor=imported.rotation_anchor,
        pivots=imported.pivots,
    )
    print(f"placed {len(tiles)} tiles in 3000x3000 clip")

    polys = [Polygon(t.polygon) for t in tiles]
    polys = [p for p in polys if p.is_valid and not p.is_empty]
    sum_area = sum(p.area for p in polys)
    union = unary_union(polys)
    ua = union.area
    rel = abs(sum_area - ua) / ua if ua else float("inf")
    print(f"sum(tile.area) = {sum_area:.1f}")
    print(f"union area     = {ua:.1f}")
    print(f"gap/overlap    = {rel*100:.4f}%")

    # Central-region coverage: a proper tiling fully covers any region not
    # touching the clip edges.
    inner = union.intersection(Polygon([(-500, -500), (500, -500),
                                         (500, 500), (-500, 500)]))
    cover = inner.area / (1000 * 1000)
    print(f"central 1000x1000 coverage = {cover*100:.2f}%")

    ok = rel < 0.01 and cover > 0.99
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
