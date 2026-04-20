# Tessera — session handoff

Written 2026-04-20 at the end of the p3-tessellation + pattern-runtime session. This is the "what's loaded, what's working, what to do next, what to *not* relitigate" note for the next person (or next session) picking up the project.

---

## Read these first

- [CLAUDE.md](../CLAUDE.md) — Matt's working conventions, tone, and Windows gotchas. Non-optional.
- [README.md](../README.md) — stack, dev loop, repo layout, current subsystem status.

Everything below assumes you've read those.

---

## State of play

**Working end-to-end:**

- `pnpm tauri dev` boots the Rust shell, spawns the Python sidecar on an ephemeral port, shows a 3-panel React webview (ShapeLibrary / Viewport / Inspector).
- Import SVG → polygon appears in the viewport.
- **Tessellate** button → Python p3 tiler places 3 rotated copies per lattice point.
- **Map LEDs to tiles** button → each of the 1024 LEDs gets assigned to a tile (majority-area + centroid fallback).
- **Play** button → selected pattern ticks at 60 fps in the R3F viewport, driving per-LED colours through the mapping + colour pipeline. Hot-reloads on file save.

**Two seed patterns:** `patterns/solid.js` (hue shifts over time, every LED same colour) and `patterns/tile-rainbow.js` (each tile gets its own phase based on centroid position — makes the LED-to-tile mapping obvious).

**Two seed motifs:** `assets/shapes/p3-hex-plain.svg` (plain regular hexagon, mathematical sanity check — should tile with zero gaps) and `assets/shapes/p3-lizard-generated.svg` (lizard-ish tile with parameterised bumps, built via the Heesch construction).

---

## The p3 rabbit hole — read this before "fixing" the tiler

Matt and I burned a meaningful chunk of session time on "why doesn't my lizard tile interlock?". Here is what is actually true, so the next session doesn't rediscover it:

1. **A proper p3 tile is not just any lizard outline.** The boundary must be constructed so that three copies rotated by 120° around specific vertices fit together with no gaps and no overlap. Arbitrary SVG tracings (the Blender-render lizard Matt first tried; a Wikimedia traced silhouette) are **not** p3 tiles and will never interlock, regardless of how the tiler is configured.

2. **Public-domain p3 lizard SVGs don't exist in polygon form.** Sean Michael Ragan's and mus.org.uk's files are laser-cut line segments (see [geometry/scripts/extract_lizard.py](../geometry/scripts/extract_lizard.py) — a working extractor that chains line segments via `shapely.ops.polygonize`, but the source files only contain the combined *outer hull* of three interlocking lizards, not individual per-lizard outlines). Escher's originals are under copyright until 2042.

3. **The right move is to generate tiles procedurally** via the Heesch hexagon-with-pivots construction. This is what [geometry/scripts/generate_p3_tile.py](../geometry/scripts/generate_p3_tile.py) does. Mathematical justification:

   - Regular hexagon, vertices V₀..V₅ at angles k·60°.
   - Pivots V₀, V₂, V₄ — alternating vertices — are 3-fold rotation centres.
   - At pivot V₀, the direction to V₁ is at 120° and the direction to V₅ is at 240°. Rotating any point on side V₀→V₁ by 120° CCW around V₀ lands exactly on the mirror position of side V₅→V₀ (verified: midpoint of V₀→V₁ = (0.75, 0.433) rotates to (0.75, −0.433) = midpoint of V₅→V₀).
   - So we pick three **free** signature curves (one per pivot, each a polyline from that pivot to the adjacent non-pivot). The other three edges are **locked**: each is the reversed 120° CCW rotation of the free curve around its pivot.
   - Output is a six-edged deformed hexagon with provable p3 tiling property.

4. **The tiler is already correct for a proper p3 motif.** [`geometry/tessera/tessellate.py`](../geometry/tessera/tessellate.py) places three motif copies at each lattice point, rotated 0°/120°/240° around the `anchor`. The anchor defaults to the motif centroid (which is wrong for a p3 tile) but is user-scrubbable from the Inspector. For generated tiles, the correct anchor is stored in the sidecar JSON file (e.g. `p3-lizard-generated.json` → `pivots_svg_coords[0]`); the tiler doesn't read that file yet (see next-steps).

5. **Don't fall back to "hex cells with lizard as skin" without asking Matt.** He explicitly rejected this as last-resort. The mathematical approach works; don't pre-empt it.

---

## What to do next

Ordered by priority for the lizard-first milestone. Ask before deviating.

### 1. Auto-set the anchor from the tile's sidecar JSON

The p3 generator writes `p3-lizard-generated.json` alongside the SVG, containing pivot coordinates in SVG-local units. Currently the UI doesn't read this file, so after importing `p3-lizard-generated.svg` the user has to scrub the anchor sliders by eye to find a pivot.

Concrete steps:

- In [geometry/tessera/shapes.py](../geometry/tessera/shapes.py), look for a sidecar `.json` next to the uploaded SVG. If present, read `pivots_svg_coords[0]`, convert to motif-local coordinates (subtract the centroid, since `import_shape_from_svg` centres the polygon on origin), and include in the `ShapeImportResponse` as `rotation_anchor`.
- In [src/components/ShapeLibrary.tsx](../src/components/ShapeLibrary.tsx), when adding a Shape from the import response, persist `rotation_anchor` on the `Shape` object.
- In [src/state/store.ts](../src/state/store.ts), when `setActiveShape` runs, also seed `panel.tiling.rotationAnchor` from the shape's default anchor.
- Users who import a hand-drawn non-p3 motif still get the centroid default; users who import a generated p3 tile get the correct anchor automatically.

### 2. Visual tiling verification

Before trusting the p3 tiler, add a small Python test that runs `tessellate` on `p3-hex-plain.svg` with correct anchor and asserts the output polygons cover the clip bounds with no gaps and no overlap. Suggested check: `shapely.ops.unary_union` of all tiles should equal the clip box (up to the `buffer(0)` fuzz). This lives in `geometry/tessera/tests/test_p3_tile.py` (not written yet).

If that test passes for the plain hex, the Heesch construction is verified and any remaining lizard weirdness is cosmetic / motif design.

### 3. Finish the pattern runtime polish

- Current render loop lives in [src/components/Viewport/LedDots.tsx](../src/components/Viewport/LedDots.tsx). Runs inside R3F `useFrame`, writes Float32 instance colours directly into the InstancedMesh buffer.
- FPS counter + frame-skip-on-slow would be nice (not critical).
- `ctx.tile(tileId, r, g, b)` helper already installed (see `tile-rainbow.js` for usage).
- Matt should add his own patterns by dropping `.js` files into `patterns/`; the Rust `notify` watcher picks them up automatically and the Inspector's pattern dropdown refreshes.

### 4. Then: single-lizard STL export

Per Matt's re-scoped plan, skip the multi-material 3MF + walls+skin + splitter + registration-jig complexity. The target is **one printed diffuser cap per lizard**, hand-assembled. Implementation:

- Python endpoint `POST /api/export/stl` takes a `PlacedTile` polygon + extrusion height (say 3 mm) and returns a path to a written STL file.
- Use `trimesh` to do the extrusion (trimesh is already in `pyproject.toml`).
- Writes to `exports/<project>/<timestamp>/lizard-<tile_id>.stl`.
- UI button "Export lizard STLs" writes one file per unique lizard shape (there are at most 3 per p3 tessellation — one per rotation variant — so this is a 3-file output).

### 5. Finally: WLED UDP DDP for real-hardware driving

Rust side, port the `wled.rs` module from VolumeCube. Hook it up to the render loop so when the pattern plays, the same buffer that drives the viewport also gets sent to WLED over UDP on port 4048. Do this *after* Matt actually has a flashed WLED controller on hand; until then there's no target to test against.

---

## Where things live

| Concern                          | File                                                                     |
|----------------------------------|--------------------------------------------------------------------------|
| Domain model (TS)                | [src/core/structure.ts](../src/core/structure.ts)                        |
| Zustand store                    | [src/state/store.ts](../src/state/store.ts)                              |
| Python sidecar client            | [src/core/api.ts](../src/core/api.ts)                                    |
| Pattern runtime + hot-reload     | [src/core/patternRuntime.ts](../src/core/patternRuntime.ts)              |
| Pattern public API (ctx.tile)    | [src/core/patternApi.ts](../src/core/patternApi.ts)                      |
| Colour pipeline                  | [src/core/colorSpace.ts](../src/core/colorSpace.ts)                      |
| 3-panel layout                   | [src/App.tsx](../src/App.tsx)                                            |
| Shape import UI                  | [src/components/ShapeLibrary.tsx](../src/components/ShapeLibrary.tsx)    |
| Transform + anchor sliders       | [src/components/Inspector.tsx](../src/components/Inspector.tsx)          |
| R3F ortho viewport               | [src/components/Viewport/index.tsx](../src/components/Viewport/index.tsx) |
| LED render loop (useFrame)       | [src/components/Viewport/LedDots.tsx](../src/components/Viewport/LedDots.tsx) |
| Tile outline rendering           | [src/components/Viewport/TileOutlines.tsx](../src/components/Viewport/TileOutlines.tsx) |
| Shape outline + anchor crosshair | [src/components/Viewport/ShapeOutline.tsx](../src/components/Viewport/ShapeOutline.tsx) |
| Python FastAPI app               | [geometry/tessera/api.py](../geometry/tessera/api.py)                    |
| SVG importer                     | [geometry/tessera/shapes.py](../geometry/tessera/shapes.py)              |
| p3 tessellator                   | [geometry/tessera/tessellate.py](../geometry/tessera/tessellate.py)      |
| LED → tile mapping               | [geometry/tessera/mapping.py](../geometry/tessera/mapping.py)            |
| Line-segment lizard extractor    | [geometry/scripts/extract_lizard.py](../geometry/scripts/extract_lizard.py) |
| p3 Heesch generator              | [geometry/scripts/generate_p3_tile.py](../geometry/scripts/generate_p3_tile.py) |
| Rust shell (main + sidecar)      | [src-tauri/src/lib.rs](../src-tauri/src/lib.rs), [src-tauri/src/sidecar.rs](../src-tauri/src/sidecar.rs) |
| Pattern file I/O commands        | [src-tauri/src/patterns.rs](../src-tauri/src/patterns.rs)                |
| Pattern file watcher             | [src-tauri/src/watch.rs](../src-tauri/src/watch.rs)                      |

---

## Conventions that will trip you up if you ignore them

From [CLAUDE.md](../CLAUDE.md), restated because they matter:

- **Terse updates to Matt.** One sentence per step. No step lists, no diff summaries, no end-of-turn recaps.
- **Ask before committing, pushing, or doing anything destructive.** Auth is explicit and scoped — a "yes push" for one commit does not authorise the next.
- **End-to-end implementation.** Matt doesn't write code. Don't hand him step-by-step instructions and ask him to copy-paste; just do it.
- **Windows paths in bash.** `/c/Users/Matt/...`, forward slashes, unix shell syntax. Cargo is not on bash PATH — invoke by absolute path `/c/Users/Matt/.cargo/bin/cargo.exe`. Python is `py -3` because Windows Store aliases hijack `python`.
- **Kill the running tessera.exe before `cargo check`** — the .exe holds its binary open and the next link fails.
- **Non-reactive 60 fps hot paths.** Pattern render state lives in refs inside `LedDots.tsx` + `useFrame`. Do not leak frame counters, buffers, or timing into Zustand.
- **Python for geometry only.** Hardware I/O stays in Rust.

---

## Last-commit state

As of the commit immediately preceding this handoff, `pnpm typecheck` is clean, `pnpm tauri dev` boots end-to-end, the p3 generator produces valid tiles, and the extractor script successfully recovers a 71-vert polygon from the Ragan lizard SVG (though that polygon is the outer hull of the full 3-lizard tessellation, not a single lizard — see the p3 rabbit hole section above). Re-run `generate_p3_tile.py` after editing signatures to regenerate the seed lizard.

To smoke-test without the full Tauri stack:

```bash
# Terminal 1 — sidecar
cd geometry && uv run tessera-api --port 8765

# Terminal 2 — curl the pipeline
curl -s http://127.0.0.1:8765/api/health
curl -s -X POST http://127.0.0.1:8765/api/tessellate \
  -H "Content-Type: application/json" \
  -d '{ "polygon": [[-50,-50],[50,-50],[50,50],[-50,50]],
        "group": "p3", "clip_bounds": {"min_x":-160,"min_y":-160,"max_x":160,"max_y":160},
        "lattice_scale": 1.0, "anchor": [0, 0] }'
```

Good luck.
