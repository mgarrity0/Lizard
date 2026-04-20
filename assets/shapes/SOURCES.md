# Shape source attribution

## Public-domain Escher-style lizard tile (Ragan)

- `escher-lizard-p3.svg` — single-file version. Original by Sean Michael Ragan, released into the public domain. Source: https://www.seanmichaelragan.com/html/%5B2008-04-18%5D_MC_Escher_lizard_vector_art.shtml
- `escher-lizard-p3-simple.svg`, `escher-lizard-p3-detail.svg` — Ponoko laser-cut wrappers of the same geometry. Source: https://mus.org.uk/teapot/tesselating-lizards/ ("public domain, do what you like with them").
- `escher-lizard-p3-single.svg` — derived work. A single closed polygon extracted from the Ragan geometry via `geometry/scripts/extract_lizard.py` (line-segment chaining + `shapely.ops.polygonize`).

Ragan's piece is a "geometrically rigorous redrawing" of the Escher motif built from scratch using rotational transforms, not a reproduction of Escher's copyrighted originals. Escher's own works remain under copyright until 2042.

## Procedurally generated tiles

- `p3-hex-plain.svg`, `p3-hex-plain.json` — plain regular hexagon with alternating-pivot annotations. Sanity check for the p3 tiler (should tessellate with zero gaps).
- `p3-lizard-generated.svg`, `p3-lizard-generated.json` — lizard-ish tile built via the Heesch hexagon-with-pivots construction. Parameterised bumps for head / legs / tail. See `geometry/scripts/generate_p3_tile.py` for the generator; edit the signature arrays to iterate on the silhouette.

Each `.json` sidecar contains:
- `hexagon_radius` — the base R used by the generator.
- `lattice_const` — distance between adjacent 3-fold rotation centres (= R·√3).
- `pivots_svg_coords` — the three rotation-centre vertices in the SVG's own coordinate space.
