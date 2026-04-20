"""LED -> tile assignment.

Each LED is tested against the placed tile polygons with one of two rules:

* ``majority-area``: approximate the LED as a small disc (radius = half pitch),
  compute intersection area with each tile, assign to the tile with the
  largest overlap. Ties broken by centroid containment.
* ``centroid``: classic point-in-polygon test on the LED centre.

The returned mapping uses the tile ids verbatim. LEDs that fall outside every
tile are excluded from the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from shapely.geometry import Point, Polygon
from shapely.prepared import prep
from shapely.strtree import STRtree

Rule = Literal["majority-area", "centroid"]


@dataclass
class PlacedTileRef:
    id: str
    polygon: list[tuple[float, float]]


def map_leds_to_tiles(
    tiles: list[PlacedTileRef],
    led_positions: list[tuple[float, float]],
    rule: Rule = "majority-area",
    led_radius: float = 5.0,
) -> dict[str, list[int]]:
    """Assign each LED to at most one tile."""
    if not tiles or not led_positions:
        return {t.id: [] for t in tiles}

    shapely_tiles: list[Polygon] = []
    for t in tiles:
        p = Polygon(t.polygon)
        if not p.is_valid:
            p = p.buffer(0)
        shapely_tiles.append(p)

    tree = STRtree(shapely_tiles)
    prepared = [prep(p) for p in shapely_tiles]
    out: dict[str, list[int]] = {t.id: [] for t in tiles}

    for i, (x, y) in enumerate(led_positions):
        candidates = tree.query(Point(x, y).buffer(max(led_radius, 0.01)))
        if len(candidates) == 0:
            continue
        # candidates is an array of indices into shapely_tiles
        best_idx = None
        best_score = -1.0

        if rule == "centroid":
            for idx in candidates:
                if prepared[int(idx)].contains(Point(x, y)):
                    best_idx = int(idx)
                    break
        else:  # majority-area
            disc = Point(x, y).buffer(led_radius)
            for idx in candidates:
                inter = shapely_tiles[int(idx)].intersection(disc).area
                if inter > best_score:
                    best_score = inter
                    best_idx = int(idx)
            # If no tile had any overlap, fall back to centroid test.
            if best_score <= 0:
                best_idx = None
                for idx in candidates:
                    if prepared[int(idx)].contains(Point(x, y)):
                        best_idx = int(idx)
                        break

        if best_idx is not None:
            out[tiles[best_idx].id].append(i)

    return out
