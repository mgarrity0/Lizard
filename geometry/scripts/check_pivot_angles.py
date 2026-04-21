"""Measure the interior angle at each pivot. For p3 to tile cleanly the
interior angle at each 3-fold pivot must be exactly 120°."""
from __future__ import annotations
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def parse_raw_path(svg_text):
    m = re.search(r'<path[^>]*\bd="([^"]*)"', svg_text, re.S)
    d = m.group(1)
    nums = [float(x) for x in re.findall(r'[-+]?\d+(?:\.\d+)?', d)]
    if len(nums) % 2:
        nums = nums[:-1]
    pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) >= 2 and math.hypot(out[0][0] - out[-1][0],
                                     out[0][1] - out[-1][1]) < 1e-3:
        out.pop()
    return out


def parse_pivots(svg_text):
    m = re.search(r'data-p3-pivots="([^"]*)"', svg_text)
    out = []
    for tok in m.group(1).strip().split():
        x, y = tok.split(",")
        out.append((float(x), float(y)))
    return out


def nearest_index(poly, target):
    best_i, best_d = 0, float("inf")
    for i, p in enumerate(poly):
        d = (p[0] - target[0]) ** 2 + (p[1] - target[1]) ** 2
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def interior_angle(poly, idx):
    """Return the (signed) interior angle at poly[idx], in degrees.
    Uses the prev- and next-vertex directions to compute the turn angle."""
    n = len(poly)
    prev_v = poly[(idx - 1) % n]
    here = poly[idx]
    next_v = poly[(idx + 1) % n]
    v_in = (here[0] - prev_v[0], here[1] - prev_v[1])   # into here
    v_out = (next_v[0] - here[0], next_v[1] - here[1])  # out of here
    # Interior angle between (-v_in) (pointing back along incoming edge)
    # and v_out (pointing forward). Measured through polygon interior.
    a_in = math.atan2(v_in[1], v_in[0])
    a_out = math.atan2(v_out[1], v_out[0])
    exterior = ((a_out - a_in) + math.pi) % (2 * math.pi) - math.pi
    # Interior = 180° - exterior (for CCW polygon); for CW, flip sign.
    interior = math.pi - exterior
    return math.degrees(interior)


def main():
    repo = Path(__file__).resolve().parents[2]
    src = repo / "assets" / "shapes" / "lizard.svg"
    svg_text = src.read_text(encoding="utf-8")
    poly = parse_raw_path(svg_text)
    pivots = parse_pivots(svg_text)
    print(f"polygon: {len(poly)} vertices")
    for k, p in enumerate(pivots):
        idx = nearest_index(poly, p)
        dist = math.hypot(poly[idx][0] - p[0], poly[idx][1] - p[1])
        ang = interior_angle(poly, idx)
        print(f"pivot {k}: idx={idx}, snap_dist={dist:.3f}, "
              f"interior_angle={ang:.3f}° (target=120°)")
    # Report the winding
    sa = sum(poly[i][0] * poly[(i+1) % len(poly)][1]
             - poly[(i+1) % len(poly)][0] * poly[i][1]
             for i in range(len(poly))) / 2
    print(f"signed area: {sa:.1f} ({'CCW' if sa > 0 else 'CW'})")


if __name__ == "__main__":
    main()
