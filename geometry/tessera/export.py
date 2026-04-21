"""Export helpers — STL extrusion + WLED preset/ledmap generation.

STL: flat-extrude a 2D polygon to a 3D mesh via trimesh.  For the lizard
panel this produces one diffuser-cap STL per unique tile shape.  In p3
all three rotation variants are congruent (they're rotations of the same
motif), so a single STL is usually sufficient and the user rotates copies
by hand at placement time.

WLED preset + ledmap: the panel's LEDs are wired as a single serpentine
chain, but each lizard covers LEDs whose chain-order indices are
discontiguous.  WLED segments only span contiguous index ranges, so to
give each lizard its own segment we generate a *ledmap* that reorders the
physical LEDs so every lizard's LEDs are contiguous in logical space, and
then the preset's segments become trivial start/stop ranges over the
reordered chain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import trimesh
from shapely.geometry import Polygon


# ---------- STL ----------


@dataclass
class StlExportRequest:
    polygon: list[tuple[float, float]]
    height_mm: float
    out_path: str
    name: str = "lizard"
    # When > 0, extrude a picture-frame ring of that thickness instead of a
    # solid plate. The result is hollow — open bottom. Useful as a
    # stand-off / diffuser retainer that clips around the LED cluster.
    wall_thickness_mm: float = 0.0
    # When > 0 AND wall_thickness > 0, put a solid top cap of this thickness
    # on the hollow shape. Walls go from z=0 to (height - cap); cap sits
    # from (height - cap) to height. Set to 0 for open-top (no cap).
    cap_thickness_mm: float = 0.0


def export_stl(req: StlExportRequest) -> str:
    """Extrude a 2D polygon (or a ring of its inset) to an STL mesh.
    Returns the absolute output path.

    The polygon must be in mm (world units). The resulting mesh sits on
    z=0 and rises +z by ``height_mm``.

    If ``wall_thickness_mm > 0``, the output is an annular ring between the
    original boundary and the inset-by-thickness boundary. Raises if the
    thickness exceeds the shape's narrowest feature (inset goes empty).
    """
    out = Path(req.out_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    poly = Polygon(req.polygon)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty:
        raise ValueError("empty polygon — nothing to extrude")

    height = max(0.1, req.height_mm)
    wt = req.wall_thickness_mm or 0.0

    if wt > 0:
        # Mitre joins preserve sharp corners on the inset boundary.
        inner = poly.buffer(-wt, join_style=2)
        if inner.is_empty:
            raise ValueError(
                f"wall thickness {wt:.2f}mm exceeds the shape's narrowest "
                f"feature — inset collapsed to empty"
            )
        # If thin bridges in the motif got cut, shapely returns MultiPolygon.
        # Keep the biggest piece so we still produce a valid ring.
        if inner.geom_type == "MultiPolygon":
            inner = max(inner.geoms, key=lambda g: g.area)
        ring = poly.difference(inner)
        if ring.is_empty:
            raise ValueError("wall ring is empty — thickness probably too small")

        cap_t = req.cap_thickness_mm or 0.0
        if cap_t >= height:
            raise ValueError(
                f"cap thickness {cap_t:.2f}mm must be less than total height "
                f"{height:.2f}mm"
            )

        if cap_t > 0:
            # Walls from z=0 to (height - cap_t); solid cap on top.
            walls_h = height - cap_t
            wall_mesh = _extrude_any(ring, walls_h)
            cap_mesh = _extrude_any(poly, cap_t)
            cap_mesh.apply_translation([0, 0, walls_h])
            mesh = trimesh.util.concatenate([wall_mesh, cap_mesh])
        else:
            # Open-top hollow frame, full height.
            mesh = _extrude_any(ring, height)
    else:
        mesh = _extrude_any(poly, height)

    mesh.export(out)
    return str(out)


def _extrude_any(geom, height: float):
    """Extrude a Polygon or MultiPolygon to a trimesh.  MultiPolygon pieces
    are extruded independently and concatenated."""
    if geom.geom_type == "MultiPolygon":
        return trimesh.util.concatenate(
            [trimesh.creation.extrude_polygon(g, height) for g in geom.geoms]
        )
    return trimesh.creation.extrude_polygon(geom, height)


# ---------- WLED preset + ledmap ----------


@dataclass
class WledExportRequest:
    tile_leds: dict[str, list[int]]  # tile_id → chain-order LED indices
    total_leds: int
    out_dir: str
    preset_id: int = 1
    preset_name: str = "Lizard tessellation"
    ledmap_id: int = 1


def build_ledmap(
    tile_leds: dict[str, list[int]], total_leds: int
) -> tuple[list[int], dict[str, tuple[int, int]]]:
    """Build a WLED ledmap.

    Returns:
      - ``logical_to_physical`` — a list of length ``total_leds`` where
        position ``i`` holds the physical LED index that WLED should light
        when it writes its logical LED ``i``.
      - ``segments`` — dict of ``tile_id → (logical_start, logical_stop)``
        (stop is exclusive, matching WLED conventions).

    Tiles are emitted in stable sort order by tile id.  Unmapped LEDs
    (present physically but not claimed by any tile) land at the end.
    """
    claimed: set[int] = set()
    logical_to_physical: list[int] = []
    segments: dict[str, tuple[int, int]] = {}

    for tile_id in sorted(tile_leds.keys()):
        leds = tile_leds[tile_id]
        if not leds:
            continue
        start = len(logical_to_physical)
        for idx in leds:
            if idx < 0 or idx >= total_leds or idx in claimed:
                continue
            logical_to_physical.append(idx)
            claimed.add(idx)
        stop = len(logical_to_physical)
        if stop > start:
            segments[tile_id] = (start, stop)

    # Append any un-mapped physical LEDs at the end so the map covers the
    # full chain length (WLED expects a map the same length as the strip).
    for phys in range(total_leds):
        if phys not in claimed:
            logical_to_physical.append(phys)

    return logical_to_physical, segments


def build_wled_preset(
    segments: dict[str, tuple[int, int]],
    preset_id: int,
    preset_name: str,
) -> dict[str, Any]:
    """Build a WLED preset JSON payload with one segment per tile.

    Compatible with WLED 0.14+ preset.json format.  The segment colour
    defaults to dim white; edit in the WLED UI or overwrite programatically
    before saving.
    """
    seg_list: list[dict[str, Any]] = []
    for i, (tile_id, (start, stop)) in enumerate(sorted(segments.items())):
        seg_list.append({
            "id": i,
            "n": tile_id,
            "start": start,
            "stop": stop,
            "grp": 1,
            "spc": 0,
            "of": 0,
            "on": True,
            "frz": False,
            "bri": 200,
            "col": [[128, 128, 128], [0, 0, 0], [0, 0, 0]],
            "fx": 0,
            "sx": 128,
            "ix": 128,
            "pal": 0,
            "sel": i == 0,
            "rev": False,
            "mi": False,
        })
    return {
        str(preset_id): {
            "n": preset_name,
            "seg": seg_list,
        }
    }


def export_wled(req: WledExportRequest) -> dict[str, Any]:
    """Write three files into ``req.out_dir`` and return their paths plus
    some summary stats:

    - ``mapping.json`` — human-readable ``{tile_id: [phys_led_idx, ...]}``
    - ``ledmap<N>.json`` — WLED ledmap (uploaded to SPIFFS as ``ledmap1.json``
      by default; WLED 0.14+ looks for ``ledmap<id>.json``).
    - ``wled-preset.json`` — WLED preset with one segment per tile.
    """
    out = Path(req.out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    # 1. Raw mapping (human reference).
    mapping_path = out / "mapping.json"
    mapping_path.write_text(
        json.dumps(req.tile_leds, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # 2. Ledmap + preset.
    logical_to_physical, segments = build_ledmap(req.tile_leds, req.total_leds)
    ledmap_payload = {"map": logical_to_physical}
    ledmap_path = out / f"ledmap{req.ledmap_id}.json"
    ledmap_path.write_text(
        json.dumps(ledmap_payload),
        encoding="utf-8",
    )

    preset_payload = build_wled_preset(segments, req.preset_id, req.preset_name)
    preset_path = out / "wled-preset.json"
    preset_path.write_text(
        json.dumps(preset_payload, indent=2),
        encoding="utf-8",
    )

    mapped_leds = sum(stop - start for start, stop in segments.values())
    return {
        "mapping_path": str(mapping_path),
        "ledmap_path": str(ledmap_path),
        "preset_path": str(preset_path),
        "segments": len(segments),
        "mapped_leds": mapped_leds,
    }
