"""Auto-detect p3 pivots on a hand-drawn Escher lizard outline.

Key insight: at a 3-fold pivot P, rotating the polygon 120° around P sends
P's forward arc onto P's backward arc. On hand-drawn geometry, boundary
intersections never coincide exactly (so shapely.boundary.intersection
returns a MultiPoint of crossings, not a LineString), but the *local arc
rotation error* remains small.

Test:  arc_error(P, θ, K) = RMS_{k=1..K} |rotate(poly[i+k], P, θ) - poly[i-k]|

For θ ∈ {+120°, -120°} (pick minimum over both senses so we're agnostic
to polygon traversal direction). At a true pivot, arc_error ≪ tile size.
At a random vertex, arc_error ~ tile size.

We also need to test GLOBAL validity — a small local arc can occur at a
spurious vertex inside a smooth stretch. So: after ranking by arc_error,
we confirm each candidate by running the tessellator and measuring gap.

Raw SVG vertices (not flattened/simplified) are used so a candidate can
coincide with a user-drawn corner.
"""

from __future__ import annotations

import math
import re
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from tessera.tessellate import ClipBounds, Transform2D, tessellate


def parse_raw_path(svg_text: str) -> list[tuple[float, float]]:
    m = re.search(r'<path[^>]*\bd="([^"]*)"', svg_text, re.S)
    if not m:
        raise ValueError("no <path d=...> in SVG")
    d = m.group(1)
    nums = [float(x) for x in re.findall(r'[-+]?\d+(?:\.\d+)?', d)]
    if len(nums) % 2:
        nums = nums[:-1]
    pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) >= 2 and math.hypot(out[0][0] - out[-1][0],
                                     out[0][1] - out[-1][1]) < 1e-3:
        out.pop()
    return out


def rotate_pt(p, centre, angle_deg):
    th = math.radians(angle_deg)
    c, s = math.cos(th), math.sin(th)
    dx, dy = p[0] - centre[0], p[1] - centre[1]
    return (dx * c - dy * s + centre[0], dx * s + dy * c + centre[1])


def arc_rotation_error(poly, i, angle_deg, arc_len):
    n = len(poly)
    P = poly[i]
    total = 0.0
    for k in range(1, arc_len + 1):
        fwd = poly[(i + k) % n]
        bwd = poly[(i - k) % n]
        fr = rotate_pt(fwd, P, angle_deg)
        dx = fr[0] - bwd[0]
        dy = fr[1] - bwd[1]
        total += dx * dx + dy * dy
    return math.sqrt(total / arc_len)


def global_overlap(poly, P):
    """Area overlap ratio of poly with poly rotated 120° around P."""
    orig = Polygon(poly)
    if not orig.is_valid:
        orig = orig.buffer(0)
    rot = Polygon([rotate_pt(q, P, 120.0) for q in poly])
    if not rot.is_valid:
        rot = rot.buffer(0)
    try:
        return orig.intersection(rot).area / orig.area if orig.area else float("inf")
    except Exception:
        return float("inf")


def evaluate_tiling(poly, pivots):
    arr = np.asarray(poly, dtype=float)
    cx, cy = float(arr[:, 0].mean()), float(arr[:, 1].mean())
    centred = [(x - cx, y - cy) for x, y in poly]
    cp = [(p[0] - cx, p[1] - cy) for p in pivots]
    pd = math.hypot(cp[0][0] - cp[1][0], cp[0][1] - cp[1][1])
    half = pd * 2.5
    placed = tessellate(
        polygon=centred, group="p3",
        global_transform=Transform2D(scale=1.0, rotation_deg=0.0,
                                     offset=(0.0, 0.0)),
        clip_bounds=ClipBounds(min_x=-half, min_y=-half,
                               max_x=half, max_y=half),
        lattice_scale=1.0, anchor=cp[0], pivots=cp,
    )
    polys = [Polygon(t.polygon) for t in placed]
    polys = [p for p in polys if p.is_valid and not p.is_empty]
    sum_area = sum(p.area for p in polys)
    union = unary_union(polys)
    ua = union.area if not union.is_empty else 0.0
    return len(placed), abs(sum_area - ua) / ua if ua else float("inf")


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    src = repo / "assets" / "shapes" / "lizard.svg"

    svg_text = src.read_text(encoding="utf-8")
    poly = parse_raw_path(svg_text)
    n = len(poly)
    print(f"parsed {n} raw SVG vertices")

    # Tile diameter (for normalizing arc error)
    arr = np.asarray(poly, dtype=float)
    span = float(max(arr[:, 0].max() - arr[:, 0].min(),
                     arr[:, 1].max() - arr[:, 1].min()))
    print(f"tile span ≈ {span:.1f}")

    # Phase 1: local arc-rotation error at every vertex.
    # arc_len scaled so we sample ~1/30 of perimeter.
    ARC_LEN = max(5, n // 30)
    print(f"\nphase 1: local arc-rotation error (arc_len={ARC_LEN})")
    scores: list[tuple[int, float]] = []
    for i in range(n):
        e_pos = arc_rotation_error(poly, i, +120.0, ARC_LEN)
        e_neg = arc_rotation_error(poly, i, -120.0, ARC_LEN)
        scores.append((i, min(e_pos, e_neg)))
    scores.sort(key=lambda s: s[1])

    print(f"  top-30 lowest-arc-error vertices:")
    for i, e in scores[:30]:
        x, y = poly[i]
        ov = global_overlap(poly, poly[i])
        print(f"    idx={i:3d}  ({x:+8.2f},{y:+8.2f})  "
              f"arc_err={e:7.3f}  overlap={ov*100:6.2f}%")

    # Phase 2: non-max suppression + filter by global overlap.
    # True pivots have both low arc error AND low global overlap.
    MIN_SEP = max(5, n // 20)
    filtered = []
    for i, e in scores:
        if e / span > 0.10:  # arc_err must be ≤ 10% of tile span
            continue
        if any(min((i - j) % n, (j - i) % n) < MIN_SEP for j, _ in filtered):
            continue
        ov = global_overlap(poly, poly[i])
        if ov > 0.05:  # ≤5% global overlap
            continue
        filtered.append((i, e))
        if len(filtered) >= 12:
            break

    print(f"\nphase 2: {len(filtered)} candidates after NMS + overlap filter")
    for i, e in filtered:
        x, y = poly[i]
        print(f"    idx={i:3d}  ({x:+8.2f},{y:+8.2f})  arc_err={e:.3f}")

    if len(filtered) < 3:
        print("FAILED: <3 candidates")
        return 1

    # Phase 3: brute-force equilateral triples, score by tiling gap.
    EQ_DEV_MAX = 0.04
    cand_idx = [c[0] for c in filtered]
    triples = []
    for tr in combinations(cand_idx, 3):
        p0, p1, p2 = (poly[i] for i in tr)
        d01 = math.hypot(p0[0] - p1[0], p0[1] - p1[1])
        d12 = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
        d20 = math.hypot(p2[0] - p0[0], p2[1] - p0[1])
        dmax, dmin = max(d01, d12, d20), min(d01, d12, d20)
        if dmax == 0:
            continue
        dev = (dmax - dmin) / dmax
        if dev > EQ_DEV_MAX:
            continue
        triples.append((dev, tr, dmax))
    triples.sort(key=lambda t: t[0])
    print(f"\nphase 3: {len(triples)} equilateral triples (≤{EQ_DEV_MAX*100:.0f}% dev)")

    best: tuple[float, tuple[int, int, int], float] | None = None
    for dev, tr, side in triples:
        pivots = [poly[i] for i in tr]
        nc, gap = evaluate_tiling(poly, pivots)
        print(f"  idx={tr}  side={side:6.1f}  eq_dev={dev*100:4.1f}%  "
              f"n={nc:3d}  gap={gap*100:7.4f}%")
        if best is None or gap < best[0]:
            best = (gap, tr, side)

    if best is None:
        print("FAILED: no equilateral triples found")
        return 1

    best_gap, best_tr, best_side = best
    best_pivots = [poly[i] for i in best_tr]
    print(f"\nBEST vertex-triple: idx={best_tr}  side={best_side:.1f}  gap={best_gap*100:.4f}%")
    for i in best_tr:
        x, y = poly[i]
        print(f"  ({x:.3f}, {y:.3f})")

    pivots_attr = " ".join(f"{x:.6f},{y:.6f}" for x, y in best_pivots)
    new_text = re.sub(r'\s*data-p3-pivots="[^"]*"', "", svg_text)
    new_text = re.sub(
        r"<svg([^>]*)>",
        lambda m: f'<svg{m.group(1)} data-p3-pivots="{pivots_attr}">',
        new_text, count=1,
    )
    src.write_text(new_text, encoding="utf-8")
    print(f"\nwrote {src}")
    if best_gap < 0.01:
        print("PASS: residual gap < 1%")
        return 0
    print(f"WARN: residual gap {best_gap*100:.2f}%")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
