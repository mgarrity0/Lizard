"""Iterative p3 fish tile generator.

Uses the same Heesch hexagon-pivot construction as
`generate_p3_tile.py` — see that file's docstring for the underlying
math (regular hexagon, 3 alternating pivots, 3 free signature curves
around the outline, 3 locked curves derived by 120° CCW rotation around
the shared pivot).

This generator is for the **fish** iteration. Each session we bump
`STAGE` and edit the signature definitions below; running the script
writes a fresh `assets/shapes/p3-fish-generated.svg` plus a sibling
`.json` metadata file.

Design decisions still open (pick them as we iterate with Matt):

  * Pivot-to-feature mapping — which three features of the fish land at
    V₀ / V₂ / V₄. A pivot is where three fish meet, so it's a "contact
    point" of the outline, typically a tail tip, mouth, or fin tip.
  * Free-edge content — the polyline shape between each pivot and the
    adjacent non-pivot vertex. Simple (t, amp) bump tuples work well;
    positive amp bulges outward, negative amp carves inward.

Stage 0 = plain hexagon (straight signatures). The first sculpted
stages should only change ONE signature at a time so the mirror-via-
rotation behaviour is visually obvious.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# Reuse the shared p3 builder from the lizard generator so both tiles
# go through the same (known-correct) rotation math.
from generate_p3_tile import (
    Point,
    build_p3_tile,
    hex_vertices,
    lizard_signature,
    write_meta,
    write_svg,
)

# Bump this every time we iterate so the filename + metadata capture
# which version of the design the SVG came from.
STAGE = 1

# Hexagon radius in motif-local units. Only affects absolute size; the
# app's globalTransform.scale slider handles physical sizing.
R = 100.0


def stage0_signatures(V: list[Point]) -> tuple[list[Point], list[Point], list[Point]]:
    """Plain hexagon — straight signatures on all three free edges.

    At this stage the tile IS a regular hexagon. It's the mathematical
    baseline: proves the tessellator interlocks (6-sided cell tiles
    trivially under p3), and lets Matt eyeball where the three pivot
    vertices end up on the outline before we commit to a pivot-to-fish-
    feature mapping.
    """
    sig_0 = [V[0], V[1]]  # free side from pivot V₀ to non-pivot V₁
    sig_2 = [V[2], V[3]]  # free side from pivot V₂ to non-pivot V₃
    sig_4 = [V[4], V[5]]  # free side from pivot V₄ to non-pivot V₅
    return sig_0, sig_2, sig_4


def stage1_signatures(V: list[Point]) -> tuple[list[Point], list[Point], list[Point]]:
    """Stage 1 — one tail-flare bump on the free edge leaving the tail tip.

    V₀ is the tail tip. The free edge V₀→V₁ runs along one side of the
    tail. One outward bump on this edge creates part of a tail-fin lobe;
    the locked partner V₅→V₀ (= sig_0 rotated +120° around V₀, reversed)
    auto-produces the mirror bump on the other side of the tail, so
    together they form a symmetric tail fin.

    `sig_2` and `sig_4` stay straight so the one bump's effect is
    visually isolated.

    If the bump comes out inward (carved) instead of outward (bulged)
    when rendered in Tessera, flip the sign of `amp` below and regen.
    """
    sig_0 = lizard_signature(V[0], V[1], [(0.4, 0.25)])
    sig_2 = [V[2], V[3]]
    sig_4 = [V[4], V[5]]
    return sig_0, sig_2, sig_4


def signatures_for_stage(stage: int, V: list[Point]) -> tuple[list[Point], list[Point], list[Point]]:
    """Dispatch table for each design stage. Add new `stageN_signatures`
    functions as we iterate."""
    if stage == 0:
        return stage0_signatures(V)
    if stage == 1:
        return stage1_signatures(V)
    raise ValueError(
        f"stage {stage} not defined yet — add stage{stage}_signatures() and route it here"
    )


def main() -> None:
    out_dir = Path(__file__).resolve().parents[2] / "assets" / "shapes"
    out_dir.mkdir(parents=True, exist_ok=True)

    V = hex_vertices(R)
    sig_0, sig_2, sig_4 = signatures_for_stage(STAGE, V)

    poly, pivots = build_p3_tile(R, sig_0, sig_2, sig_4)

    # Versioned filename so earlier stages stay on disk for comparison.
    svg_path = out_dir / f"p3-fish-stage{STAGE}.svg"
    json_path = out_dir / f"p3-fish-stage{STAGE}.json"
    write_svg(poly, svg_path, pivots=pivots)

    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    write_meta(pivots, min(xs), min(ys), json_path, R)

    # Also write a stable "current" alias the app imports — avoids changing
    # the path in the UI every iteration.
    stable_svg = out_dir / "p3-fish-generated.svg"
    stable_json = out_dir / "p3-fish-generated.json"
    stable_svg.write_text(svg_path.read_text(encoding="utf-8"), encoding="utf-8")
    stable_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"stage {STAGE}: wrote {svg_path.name} ({len(poly)} verts) + {stable_svg.name}")
    print(f"  pivots (motif coords): {[(round(p[0], 2), round(p[1], 2)) for p in pivots]}")
    print(f"  pivot triangle side: {math.hypot(pivots[0][0] - pivots[1][0], pivots[0][1] - pivots[1][1]):.2f}")


if __name__ == "__main__":
    main()
