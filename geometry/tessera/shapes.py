"""Shape import: SVG/PNG/DXF -> shapely Polygon.

Only SVG is implemented for v1; PNG (raster trace) and DXF come later. The
SVG path is flattened to line segments via svgpathtools, joined into closed
rings, and wrapped in a shapely Polygon. Coordinates are returned in the
SVG's original units (we do not attempt to infer mm from viewBox — the
caller is expected to scale as needed in the UI).
"""

from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass
from typing import Literal
from xml.etree import ElementTree as ET

import numpy as np
from shapely.geometry import Polygon
from shapely.validation import make_valid
from svgpathtools import parse_path

SymmetryGroup = Literal["p1", "p2", "p3", "p4", "p6"]

FLATTEN_STEPS_PER_UNIT = 0.5  # ~2 samples per unit length for curve flattening


@dataclass
class ImportedShape:
    polygon: list[tuple[float, float]]  # centered on origin
    width: float
    height: float
    symmetry_hint: SymmetryGroup
    rotation_anchor: tuple[float, float]
    # The tile's 3-fold rotation centres in motif-local (centred) coords. Empty
    # for hand-drawn SVGs that carry no metadata; populated by generator tiles
    # via the `data-p3-pivots` root attribute. The tessellator uses the
    # distance between the first two pivots as the lattice constant, so
    # interlock happens automatically for tiles that carry this metadata.
    pivots: list[tuple[float, float]]
    # Offset that was subtracted to centre the polygon on origin. Tools that
    # need to emit back-to-SVG coordinates (e.g. pivot injection scripts) add
    # this to centred-frame points to recover SVG-space coordinates.
    center_offset: tuple[float, float] = (0.0, 0.0)


def import_shape_from_svg(svg_bytes: bytes) -> ImportedShape:
    """Parse an SVG blob and return a single centred, closed polygon.

    We pick the first non-empty <path> in the document. Multi-path SVGs are
    handled by unioning all paths into one polygon (they may represent a
    single motif split into multiple stroke groups).
    """
    # Strip namespaces so ElementTree doesn't nest them into tag names.
    text = svg_bytes.decode("utf-8", errors="replace")
    text = _strip_default_namespace(text)
    root = ET.fromstring(text)

    # Optional self-describing metadata: `<svg data-p3-pivots="x1,y1 x2,y2 x3,y3">`
    # Each pivot is in SVG-local coords. The first entry is the primary 3-fold
    # centre — used to auto-seed the rotation anchor below.
    pivots_attr = root.get("data-p3-pivots")

    rings: list[list[tuple[float, float]]] = []
    for path_el in root.iter("path"):
        d = path_el.get("d")
        if not d:
            continue
        path = parse_path(d)
        ring = _flatten_path(path)
        if len(ring) >= 3:
            rings.append(ring)

    if not rings:
        raise ValueError("SVG contains no <path> with a d= attribute")

    # Union all rings into a single polygon.
    polys = [Polygon(r) for r in rings if len(r) >= 3]
    polys = [p for p in polys if not p.is_empty and p.is_valid]
    if not polys:
        polys = [make_valid(Polygon(rings[0]))]
    union = polys[0]
    for p in polys[1:]:
        union = union.union(p)
    if union.is_empty:
        raise ValueError("empty polygon after union")
    # If the union is a MultiPolygon, pick the largest piece — the motif.
    if union.geom_type == "MultiPolygon":
        union = max(union.geoms, key=lambda g: g.area)
    elif union.geom_type not in ("Polygon",):
        raise ValueError(f"unsupported geometry type: {union.geom_type}")

    coords = list(union.exterior.coords)
    # Drop the duplicate closing vertex to match shapely's canonical form.
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]

    # Center on origin and measure bounds.
    arr = np.asarray(coords, dtype=float)
    cx = float(arr[:, 0].mean())
    cy = float(arr[:, 1].mean())
    centred = [(x - cx, y - cy) for (x, y) in coords]

    xs = [p[0] for p in centred]
    ys = [p[1] for p in centred]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)

    # Translate embedded pivots into motif-local (centred) coords. Empty list
    # if the SVG carries no metadata — tessellator falls back to bbox heuristic.
    pivots = _parse_pivots(pivots_attr, cx, cy)
    rotation_anchor = pivots[0] if pivots else (0.0, 0.0)

    return ImportedShape(
        polygon=centred,
        width=width,
        height=height,
        symmetry_hint=_guess_symmetry(centred),
        rotation_anchor=rotation_anchor,
        pivots=pivots,
        center_offset=(cx, cy),
    )


def _parse_pivots(
    attr: str | None, cx: float, cy: float
) -> list[tuple[float, float]]:
    if not attr:
        return []
    out: list[tuple[float, float]] = []
    for tok in attr.strip().split():
        try:
            px_str, py_str = tok.split(",")
            out.append((float(px_str) - cx, float(py_str) - cy))
        except (ValueError, IndexError):
            continue
    return out


def decode_data_source(kind: str, data_b64: str) -> bytes:
    """Decode a base64-encoded source blob."""
    if kind not in ("svg", "png", "dxf"):
        raise ValueError(f"unsupported source kind: {kind}")
    if kind != "svg":
        raise NotImplementedError(f"{kind} import not implemented yet")
    return base64.b64decode(data_b64)


# ---------- helpers ----------


def _strip_default_namespace(xml_text: str) -> str:
    # Remove xmlns="..." so tag names don't pick up {ns}path form. Crude but
    # sufficient for well-formed SVG sources.
    import re

    return re.sub(r'\sxmlns="[^"]+"', "", xml_text, count=1)


def _flatten_path(path) -> list[tuple[float, float]]:  # path: svgpathtools.Path
    """Sample a svgpathtools path into a polyline."""
    out: list[tuple[float, float]] = []
    for seg in path:
        seg_length = _seg_length(seg)
        steps = max(2, int(seg_length * FLATTEN_STEPS_PER_UNIT) + 1)
        for i in range(steps + 1):
            t = i / steps
            p = seg.point(t)
            out.append((p.real, p.imag))
    # Close the ring if the path is closed.
    if len(out) >= 2:
        dx = out[0][0] - out[-1][0]
        dy = out[0][1] - out[-1][1]
        if math.hypot(dx, dy) < 1e-6:
            out.pop()  # drop duplicate closing vertex
    return out


def _seg_length(seg) -> float:
    try:
        return float(seg.length())
    except Exception:
        return 10.0  # fallback for weirdly-defined segments


def _guess_symmetry(poly: list[tuple[float, float]]) -> SymmetryGroup:
    """Extremely lightweight symmetry hint based on rotational self-similarity."""
    if len(poly) < 12:
        return "p1"
    # Try 6, 4, 3, 2 fold rotational symmetry. A motif that is approximately
    # self-similar under rotation-by-(360/n) keeps its point cloud close to
    # itself. We score by hausdorff-ish distance averaged to the centroid.
    scores: dict[SymmetryGroup, float] = {}
    arr = np.asarray(poly, dtype=float)
    r = np.hypot(arr[:, 0], arr[:, 1])
    for n, label in ((6, "p6"), (4, "p4"), (3, "p3"), (2, "p2")):
        angle = 2 * math.pi / n
        # Rotated copy
        rotated = np.column_stack([
            arr[:, 0] * math.cos(angle) - arr[:, 1] * math.sin(angle),
            arr[:, 0] * math.sin(angle) + arr[:, 1] * math.cos(angle),
        ])
        # Mean distance from each point to the nearest original point. For
        # large N this is expensive; use radial bucketing as a cheap proxy.
        r_rot = np.hypot(rotated[:, 0], rotated[:, 1])
        scores[label] = float(abs(r.mean() - r_rot.mean()))
    best = min(scores.items(), key=lambda kv: kv[1])
    # Very crude: just take whatever matched best. p3 is the Escher lizard
    # target so if the score is close between p3 and p6, prefer p3.
    if abs(scores["p3"] - best[1]) < 1e-3:
        return "p3"
    return best[0]
