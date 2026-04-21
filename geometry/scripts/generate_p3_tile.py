"""Generate a p3 lizard tile using the Heesch hexagon-pivot construction.

Method (proven correct by direct coordinate check):
  * Regular hexagon, vertices V0..V5 at angles k·60° (k=0..5), radius R.
  * Pivots = alternating vertices V0, V2, V4 — each is a 3-fold rotation
    centre in the finished p3 tessellation.
  * The six sides split into three "free/locked" pairs around each pivot.
    At pivot V0: free side = V0→V1, locked side = V5→V0.
    At pivot V2: free side = V2→V3, locked side = V1→V2.
    At pivot V4: free side = V4→V5, locked side = V3→V4.
  * The locked side is determined by rotating the free side 120° CCW around
    the shared pivot and reversing.  Concretely: for free curve sig from
    pivot P to non-pivot N, the locked curve from rot120(N around P) back
    to P is `reversed([rot120(p around P) for p in sig])`.
  * Because adjacent tiles share boundary under p3, this construction
    guarantees gap-free, overlap-free tessellation.

Signatures (the three free edges) can be anything — straight lines give a
regular hexagon, wavy curves give a lizard-ish outline.  This script
produces both a plain hexagon (sanity check) and a lizard-ish variant,
plus writes out the pivot coordinates so the tessellator can set the
rotation anchor automatically.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


Point = tuple[float, float]


def rotate_around(p: Point, angle_deg: float, centre: Point) -> Point:
    th = math.radians(angle_deg)
    c, s = math.cos(th), math.sin(th)
    dx, dy = p[0] - centre[0], p[1] - centre[1]
    return (dx * c - dy * s + centre[0], dx * s + dy * c + centre[1])


def hex_vertices(R: float) -> list[Point]:
    """Regular hexagon, flat on the right (V0 at +x axis)."""
    return [(R * math.cos(math.radians(60 * k)), R * math.sin(math.radians(60 * k)))
            for k in range(6)]


def rotate_curve(curve: list[Point], angle_deg: float, centre: Point) -> list[Point]:
    return [rotate_around(p, angle_deg, centre) for p in curve]


def build_p3_tile(R: float, sig_0: list[Point], sig_2: list[Point],
                  sig_4: list[Point]) -> tuple[list[Point], list[Point]]:
    """Build a closed p3 tile from three signature curves.

    sig_i is a polyline from V_{2i} (pivot) to V_{2i+1} (non-pivot).
    First point of sig_i must equal V_{2i}; last point must equal V_{2i+1}.

    Returns (polygon, pivots) where polygon is the closed outline (no
    duplicate closing vertex) and pivots is the list of 3-fold rotation
    centres [V0, V2, V4].
    """
    V = hex_vertices(R)
    # Sanity: endpoints pinned
    assert _close(sig_0[0], V[0]) and _close(sig_0[-1], V[1]), "sig_0 endpoints"
    assert _close(sig_2[0], V[2]) and _close(sig_2[-1], V[3]), "sig_2 endpoints"
    assert _close(sig_4[0], V[4]) and _close(sig_4[-1], V[5]), "sig_4 endpoints"

    # Locked curves: rotate the *next* signature around its pivot and reverse.
    # Side V1→V2 (locked, around pivot V2) = reverse of rot120(sig_2 around V2)
    locked_12 = list(reversed(rotate_curve(sig_2, 120, V[2])))
    # Side V3→V4 (locked, around pivot V4) = reverse of rot120(sig_4 around V4)
    locked_34 = list(reversed(rotate_curve(sig_4, 120, V[4])))
    # Side V5→V0 (locked, around pivot V0) = reverse of rot120(sig_0 around V0)
    locked_50 = list(reversed(rotate_curve(sig_0, 120, V[0])))

    # Assemble the polygon, skipping duplicate junctions.
    poly: list[Point] = []
    poly.extend(sig_0[:-1])
    poly.extend(locked_12[:-1])
    poly.extend(sig_2[:-1])
    poly.extend(locked_34[:-1])
    poly.extend(sig_4[:-1])
    poly.extend(locked_50[:-1])

    return poly, [V[0], V[2], V[4]]


def _close(p: Point, q: Point, tol: float = 1e-6) -> bool:
    return math.hypot(p[0] - q[0], p[1] - q[1]) < tol


# ---------- signature design ----------

def lizard_signature(V_start: Point, V_end: Point, bumps: list[tuple[float, float]]) -> list[Point]:
    """Build a polyline from V_start to V_end with bumps along the way.

    `bumps` is a list of (t, amp) pairs.  Each bump inserts a point at
    parameter t along the straight line from V_start to V_end, offset
    perpendicularly by amp * side_length.  Positive amp bumps to the
    tile's *outside* (left of direction of travel); negative to the
    inside.
    """
    sx, sy = V_start
    ex, ey = V_end
    dx, dy = ex - sx, ey - sy
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L              # unit along
    nx, ny = -uy, ux                     # unit perpendicular (left of direction)

    pts: list[Point] = [V_start]
    last_t = 0.0
    for t, amp in bumps:
        assert 0 < t < 1, "bump t must be strictly between 0 and 1"
        assert t > last_t, "bumps must be ordered by t"
        last_t = t
        bx = sx + t * dx + amp * L * nx
        by = sy + t * dy + amp * L * ny
        pts.append((bx, by))
    pts.append(V_end)
    return pts


def write_svg(poly: list[Point], path: Path, pivots: list[Point] | None = None) -> None:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w, h = maxx - minx, maxy - miny
    # Shift to origin-aligned
    shifted = [(p[0] - minx, p[1] - miny) for p in poly]
    d = "M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in shifted) + " Z"
    pivot_svg = ""
    pivots_attr = ""
    if pivots:
        shifted_pivots = [(p[0] - minx, p[1] - miny) for p in pivots]
        for px, py in shifted_pivots:
            pivot_svg += (f'  <circle cx="{px:.3f}" cy="{py:.3f}" '
                          f'r="3" fill="red"/>\n')
        # Embed pivot coordinates (in SVG-local coords, post shift-to-origin)
        # on the <svg> root so the importer can auto-seed the rotation anchor
        # without a sidecar JSON. First pivot is the primary 3-fold centre.
        pivots_str = " ".join(f"{x:.6f},{y:.6f}" for x, y in shifted_pivots)
        pivots_attr = f' data-p3-pivots="{pivots_str}"'
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}" height="{h:.3f}" '
        f'viewBox="0 0 {w:.3f} {h:.3f}"{pivots_attr}>\n'
        f'  <path d="{d}" fill="#6ae3ff" fill-opacity="0.35" '
        f'stroke="#000" stroke-width="1.5"/>\n'
        f'{pivot_svg}'
        f'</svg>\n'
    )
    path.write_text(svg, encoding="utf-8")


def write_meta(pivots: list[Point], minx: float, miny: float,
               path: Path, R: float) -> None:
    """Emit a sidecar JSON with pivot coordinates (in SVG-local coords)
    and the lattice constant."""
    shifted_pivots = [(p[0] - minx, p[1] - miny) for p in pivots]
    lattice_const = math.hypot(pivots[0][0] - pivots[1][0],
                               pivots[0][1] - pivots[1][1])
    meta = {
        "hexagon_radius": R,
        "lattice_const": lattice_const,
        "pivots_svg_coords": shifted_pivots,
    }
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> None:
    out_dir = Path(__file__).resolve().parents[2] / "assets" / "shapes"
    out_dir.mkdir(parents=True, exist_ok=True)

    R = 100.0
    V = hex_vertices(R)

    # 1) Plain regular hexagon (sanity check — straight signatures)
    sig0 = [V[0], V[1]]
    sig2 = [V[2], V[3]]
    sig4 = [V[4], V[5]]
    poly, pivots = build_p3_tile(R, sig0, sig2, sig4)
    path = out_dir / "p3-hex-plain.svg"
    write_svg(poly, path, pivots=pivots)
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    write_meta(pivots, min(xs), min(ys), path.with_suffix(".json"), R)
    print(f"wrote {path} ({len(poly)} verts)")

    # 2) Lizard-ish tile with bumps that roughly suggest head, legs, tail.
    # Each signature designs ONE third of the lizard's outline; rotations
    # fill in the other three edges automatically.
    # Bumps: list of (t, amp) — amp > 0 = outward protrusion (limb),
    # amp < 0 = inward notch.
    # Signature V0→V1 (head + front limb region):
    sig0 = lizard_signature(V[0], V[1], [
        (0.20, +0.30),  # head
        (0.35, -0.15),  # neck notch
        (0.55, +0.40),  # front arm
        (0.70, -0.10),  # elbow notch
        (0.85, +0.25),  # shoulder
    ])
    # Signature V2→V3 (back + hind limb):
    sig2 = lizard_signature(V[2], V[3], [
        (0.25, +0.35),  # hip
        (0.50, -0.20),  # waist
        (0.75, +0.30),  # thigh
    ])
    # Signature V4→V5 (tail + belly):
    sig4 = lizard_signature(V[4], V[5], [
        (0.30, +0.40),  # tail tip
        (0.55, -0.10),  # tail base
        (0.75, +0.20),  # belly bump
    ])
    poly, pivots = build_p3_tile(R, sig0, sig2, sig4)
    path = out_dir / "p3-lizard-generated.svg"
    write_svg(poly, path, pivots=pivots)
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    write_meta(pivots, min(xs), min(ys), path.with_suffix(".json"), R)
    print(f"wrote {path} ({len(poly)} verts)")


if __name__ == "__main__":
    main()
