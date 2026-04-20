"""Extract ONE Escher p3 lizard outline from Ragan's line-segment SVG.

Ragan's public-domain SVG draws the tessellation as ~60 <line> elements
showing 3 interlocking lizards. We want a single closed polygon for one
lizard, which we'll save as a clean SVG the existing importer can consume.

Strategy:
  * Parse all <line> + <path> segments, collect their endpoints.
  * Snap points to a tolerance so float jitter doesn't create false duplicates.
  * Build an undirected graph (point -> list of neighbour points via segments).
  * Shared 3-fold rotation centres will have higher degree (3 lizards meet
    there → each contributes 2 edges → degree 6). Cut those nodes.
  * Walk the remaining cycles to extract one lizard polygon.
  * Pick the cycle with area closest to (total_area / 3) — that's one lizard.
"""

from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from shapely.geometry import MultiLineString, Polygon
from shapely.ops import polygonize, unary_union
from svgpathtools import parse_path


SNAP_TOL = 3.0  # units: SVG user-coords (pre-transform). Points within this are merged.


def strip_ns(xml: str) -> str:
    return re.sub(r'\sxmlns="[^"]+"', "", xml, count=1)


def parse_transform(s: str) -> tuple[float, float, float, float, float, float]:
    """Parse matrix(a,b,c,d,e,f) or return identity."""
    if not s:
        return 1, 0, 0, 1, 0, 0
    m = re.match(r"matrix\(([^)]+)\)", s.strip())
    if not m:
        return 1, 0, 0, 1, 0, 0
    parts = [float(x) for x in re.split(r"[, ]+", m.group(1).strip()) if x]
    if len(parts) != 6:
        return 1, 0, 0, 1, 0, 0
    return tuple(parts)  # type: ignore[return-value]


def apply(M, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = M
    return a * x + c * y + e, b * x + d * y + f


def snap(p: tuple[float, float]) -> tuple[float, float]:
    return (round(p[0] / SNAP_TOL) * SNAP_TOL, round(p[1] / SNAP_TOL) * SNAP_TOL)


def walk_group(el, parent_M) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Recurse through an SVG subtree, apply transforms, return edges."""
    tfm = parse_transform(el.get("transform", ""))
    # Combine parent * self: (M_parent * M_self)
    a, b, c, d, e, f = parent_M
    a2, b2, c2, d2, e2, f2 = tfm
    M = (
        a * a2 + c * b2,
        b * a2 + d * b2,
        a * c2 + c * d2,
        b * c2 + d * d2,
        a * e2 + c * f2 + e,
        b * e2 + d * f2 + f,
    )
    edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    tag = el.tag.rsplit("}", 1)[-1]

    if tag == "line":
        try:
            x1 = float(el.get("x1", "0"))
            y1 = float(el.get("y1", "0"))
            x2 = float(el.get("x2", "0"))
            y2 = float(el.get("y2", "0"))
        except ValueError:
            return edges
        p1 = snap(apply(M, x1, y1))
        p2 = snap(apply(M, x2, y2))
        if p1 != p2:
            edges.append((p1, p2))
        return edges

    if tag == "polyline" or tag == "polygon":
        pts_s = el.get("points", "")
        nums = [float(x) for x in re.split(r"[ ,]+", pts_s.strip()) if x]
        pts = list(zip(nums[0::2], nums[1::2]))
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            p1 = snap(apply(M, x1, y1))
            p2 = snap(apply(M, x2, y2))
            if p1 != p2:
                edges.append((p1, p2))
        if tag == "polygon" and len(pts) >= 2:
            p1 = snap(apply(M, *pts[-1]))
            p2 = snap(apply(M, *pts[0]))
            if p1 != p2:
                edges.append((p1, p2))
        return edges

    if tag == "path":
        # Flatten all path segments (including Bezier curves) via svgpathtools.
        d = el.get("d", "")
        if not d:
            return edges
        try:
            path = parse_path(d)
        except Exception:
            return edges
        for seg in path:
            try:
                seg_len = float(seg.length())
            except Exception:
                seg_len = 10.0
            steps = max(2, int(seg_len * 0.3) + 1)
            prev: tuple[float, float] | None = None
            for i in range(steps + 1):
                t = i / steps
                p = seg.point(t)
                xp, yp = p.real, p.imag
                cur = snap(apply(M, xp, yp))
                if prev is not None and cur != prev:
                    edges.append((prev, cur))
                prev = cur
        return edges

    # Recurse into children
    for child in el:
        edges.extend(walk_group(child, M))
    return edges


def _parse_simple_path(d: str) -> list[list[tuple[float, float]]]:
    """Parse M/m/L/l/Z path segments. Returns list of subpaths (each a list
    of (x,y) vertices). Curves (C, Q, etc.) cause the subpath to stop."""
    tokens = re.findall(r"[MmLlZzCcSsQqTtAaHhVv]|-?\d+(?:\.\d+)?", d)
    subpaths: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    i = 0
    x, y = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    cmd = ""
    while i < len(tokens):
        t = tokens[i]
        if t in "MmLlZzCcSsQqTtAaHhVv":
            cmd = t
            i += 1
            if cmd in "Zz":
                if cur and cur[0] != (x, y):
                    cur.append((start_x, start_y))
                if cur:
                    subpaths.append(cur)
                cur = []
                x, y = start_x, start_y
            continue
        # Read two numbers for M/L/m/l; bail for curve commands
        if cmd in "MmLl":
            try:
                nx = float(tokens[i])
                ny = float(tokens[i + 1])
            except (IndexError, ValueError):
                break
            i += 2
            if cmd in "mMlL":
                if cmd == "m" or cmd == "l":
                    nx += x
                    ny += y
            x, y = nx, ny
            if cmd in "Mm":
                if cur:
                    subpaths.append(cur)
                cur = [(x, y)]
                start_x, start_y = x, y
                # After M, subsequent coord pairs are implicit L
                cmd = "L" if cmd == "M" else "l"
            else:
                cur.append((x, y))
        else:
            # Unknown or curve command — stop this subpath
            break
    if cur:
        subpaths.append(cur)
    return subpaths


def find_cycles(
    edges: list[tuple[tuple[float, float], tuple[float, float]]],
    cut_degree: int = 3,
) -> list[list[tuple[float, float]]]:
    """Split the graph at nodes with degree > cut_degree, then find cycles in
    each resulting subgraph."""
    adj: dict[tuple[float, float], set[tuple[float, float]]] = defaultdict(set)
    for p1, p2 in edges:
        adj[p1].add(p2)
        adj[p2].add(p1)

    # Identify cut nodes (degree > cut_degree)
    cut_nodes = {n for n, nbrs in adj.items() if len(nbrs) > cut_degree}

    # Build subgraph without cut nodes (but keep track of which cut nodes
    # each component touches — we'll re-attach them).
    sub_adj: dict[tuple[float, float], set[tuple[float, float]]] = defaultdict(set)
    for p1, p2 in edges:
        if p1 in cut_nodes or p2 in cut_nodes:
            continue
        sub_adj[p1].add(p2)
        sub_adj[p2].add(p1)

    # Find connected components in the subgraph
    visited: set[tuple[float, float]] = set()
    components: list[set[tuple[float, float]]] = []
    for start in sub_adj:
        if start in visited:
            continue
        comp = set()
        stack = [start]
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            comp.add(n)
            stack.extend(sub_adj[n] - visited)
        components.append(comp)

    # For each component, pick neighbouring cut-node endpoints via the
    # original adjacency, and walk a cycle covering all component edges.
    cycles: list[list[tuple[float, float]]] = []
    for comp in components:
        # Build a node-set for this lizard: component + adjacent cut nodes
        nodes = set(comp)
        for n in comp:
            for nbr in adj[n]:
                if nbr in cut_nodes:
                    nodes.add(nbr)
        # Pick edges whose BOTH endpoints are in this node-set
        local_adj: dict[tuple[float, float], set[tuple[float, float]]] = defaultdict(set)
        for p1, p2 in edges:
            if p1 in nodes and p2 in nodes:
                local_adj[p1].add(p2)
                local_adj[p2].add(p1)

        # Walk: start at a degree-2 node, go until return. If degree-2
        # everywhere we get a simple cycle.
        if not local_adj:
            continue
        start = next(iter(local_adj))
        path: list[tuple[float, float]] = [start]
        prev = None
        cur = start
        while True:
            nxt = None
            for cand in local_adj[cur]:
                if cand != prev:
                    nxt = cand
                    break
            if nxt is None or nxt == start:
                break
            path.append(nxt)
            prev, cur = cur, nxt
            if len(path) > 1000:
                break  # safety
        cycles.append(path)
    return cycles


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "assets/shapes/escher-lizard-p3.svg")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else "assets/shapes/escher-lizard-single.svg")
    text = strip_ns(src.read_text(encoding="utf-8"))
    root = ET.fromstring(text)
    edges = walk_group(root, (1, 0, 0, 1, 0, 0))
    print(f"extracted {len(edges)} segments from {src}")
    # Drop the huge outer rectangle (sheet border) by area heuristic — edges
    # whose length is > 400 in world units are probably the borders.
    edges = [e for e in edges if math.hypot(e[0][0] - e[1][0], e[0][1] - e[1][1]) < 200]
    print(f"after long-edge filter: {len(edges)}")

    # Degree histogram to see structure
    deg: dict[tuple[float, float], int] = defaultdict(int)
    for p1, p2 in edges:
        deg[p1] += 1
        deg[p2] += 1
    hist: dict[int, int] = defaultdict(int)
    for v in deg.values():
        hist[v] += 1
    print(f"degree histogram: {dict(sorted(hist.items()))}")
    # List high-degree nodes
    high = [(n, d) for n, d in deg.items() if d >= 3]
    print(f"high-degree nodes (deg>=3): {len(high)}")
    for n, d in sorted(high, key=lambda x: -x[1])[:10]:
        print(f"  deg {d} at {n}")

    # Skip 2-core pruning — polygonize handles dangling edges by leaving
    # them out of the polygon set, and we don't want to prematurely remove
    # any edges that are actually part of closed regions.
    pruned_edges = list(edges)

    # Use Shapely's polygonize: it takes a set of noded LineStrings and
    # returns the closed polygonal faces. First we have to node the lines so
    # that intersections become explicit vertices.
    lines = MultiLineString(pruned_edges)
    noded = unary_union(lines)
    polys = list(polygonize(noded))
    print(f"polygonize produced {len(polys)} polygons")
    for i, p in enumerate(sorted(polys, key=lambda q: -q.area)[:8]):
        print(f"  poly {i}: area {p.area:.1f}, verts {len(p.exterior.coords) - 1}")

    # The 3 largest bounded faces are the 3 lizards. Sort by area and pick
    # the biggest (they should all have similar size for a proper p3 tile).
    big = sorted(polys, key=lambda p: -p.area)
    if not big:
        print("no polygons found")
        return 1
    best_poly = big[0]
    print(f"picked best polygon: area {best_poly.area:.1f}, "
          f"verts {len(best_poly.exterior.coords) - 1}")

    best = [(x, y) for x, y in best_poly.exterior.coords][:-1]
    xs = [p[0] for p in best]
    ys = [p[1] for p in best]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w, h = maxx - minx, maxy - miny
    # Shift to origin
    pts = [(p[0] - minx, p[1] - miny) for p in best]
    path_d = "M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in pts) + " Z"
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w:.3f}" height="{h:.3f}" viewBox="0 0 {w:.3f} {h:.3f}">\n'
        f'  <path d="{path_d}" fill="#444" stroke="#000" stroke-width="1"/>\n'
        f'</svg>\n'
    )
    dst.write_text(svg, encoding="utf-8")
    print(f"wrote {dst} ({len(best)} verts, {w:.1f} × {h:.1f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
