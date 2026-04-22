# Tessera

Tessellation and LED mapping workbench — the third entry in a desktop LED tooling suite alongside [VolumeCube](https://github.com/mgarrity0/VolumeCube) (10³ WS2815 cube) and [Orbiter](https://github.com/mgarrity0/Orbiter) (16-ft WS2815 half-dome). Tessera takes a 2D shape, tiles it across a bounded region via a wallpaper group, maps the resulting tiles onto a user-defined LED layout, and produces every artifact needed to physically build the thing — printable 3MF, laser-cuttable DXF, WLED preset, FastLED bake, and a live UDP DDP preview.

**First concrete project:** an Escher-lizard tessellating diffuser panel over a 32×32 WS2812 grid (four tiled 16×16 BTF panels at 10 mm pitch). Each lizard cell becomes one diffuser cell covering ~25–36 LEDs. Multi-material print on a Bambu A1 + AMS: black PETG walls, white PETG diffuser skin. Philosophy is **lizard-first** — ship a printed, mounted, lit panel before generalizing to other shapes, groups, and hardware targets.

---

## What Tessera does

```
 Source                Tessellate           Map LEDs             Output
 ─────                 ──────────           ────────             ──────
 SVG / PNG / DXF ──▶   Wallpaper-group ─▶   majority-area   ─▶   3MF (walls+skin)
                       tiler (p1/p2/p3/     + centroid            STL (spacer, jig)
                        p4/p6)              tiebreaker            DXF (laser overlay)
                                                                  WLED preset JSON
                                                                  FastLED .ino
                                                                  Live UDP DDP
```

Each stage is a distinct endpoint on the Python sidecar (shape import, tessellate, map, split, export) so the UI can iterate on any one step without re-running the pipeline from scratch.

---

## Architecture

Tessera is three processes cooperating inside one desktop app:

1. **Rust (Tauri shell)** — owns the window, filesystem, hardware I/O, and process supervision. Hot-reload file watching (`notify`), WLED UDP DDP (port 4048), and CRC-16/CCITT-FALSE serial framing live here. Picks an ephemeral TCP port on boot and spawns the Python sidecar on it.
2. **Python (geometry sidecar)** — FastAPI on `127.0.0.1:<ephemeral>`. All heavy 2D/3D geometry: shapely boolean ops, svgpathtools flattening, trimesh/build123d mesh extrusion, 3MF/STL/DXF export. Emits `TESSERA_READY` on stdout once uvicorn has bound the port so Rust knows when it's live.
3. **React webview** — Tauri invokes `get_sidecar_base` to hand the port to the frontend. All geometry calls go `fetch()` over HTTP; hot-path hardware calls go through `invoke()` to Rust.

```
 ┌────────────────────────────────────┐
 │ Tauri shell (Rust)                 │
 │                                    │
 │  ┌─────────────────────────────┐   │       ┌──────────────────────┐
 │  │ Webview (React + R3F)       │◀──┼──────▶│ Python sidecar        │
 │  │                             │   │ HTTP  │ (FastAPI, shapely,    │
 │  │  Shape library              │   │       │  trimesh, svgpath)    │
 │  │  R3F viewport               │   │       └──────────────────────┘
 │  │  Inspector                  │   │
 │  └─────────────────────────────┘   │       ┌──────────────────────┐
 │                                    │──────▶│ WLED hardware          │
 │  notify (hot-reload)               │ DDP   │ (ESP32 + WS2812)       │
 │  UdpSocket → WLED DDP :4048        │       └──────────────────────┘
 │  serialport (CRC-16 framing)       │
 └────────────────────────────────────┘
```

### Why a Python sidecar

Shapely (2D polygon booleans + LED-in-polygon tests), trimesh + build123d (watertight mesh extrusion, multi-material 3MF export), svgpathtools (SVG path math), and OpenSCAD (escape hatch for stubborn geometry) are substantially more mature and correct than anything in JS for this domain. VolumeCube and Orbiter didn't need them because cube/dome geometry is arithmetic on a grid. Tessera's 2D tessellation + CAD extrusion is not.

The sidecar will be bundled by PyInstaller and shipped via `tauri.conf.json` `bundle.externalBin` for packaged builds. Rust still owns hardware I/O for the 60 fps hot path — Python never touches UDP or serial.

---

## Stack

| Layer                  | Choice                                                   | Notes                                                        |
|------------------------|----------------------------------------------------------|--------------------------------------------------------------|
| Desktop shell          | Tauri 2                                                  | Matches VolumeCube + Orbiter                                 |
| Frontend               | React 18 + Vite 5 + TypeScript strict                    | Matches both prior apps                                      |
| 3D viewport            | @react-three/fiber + drei + postprocessing (Bloom)       | Ortho camera in 2D panel mode; perspective later for preview |
| UI state               | Zustand 5                                                | 60 fps hot paths use module-level singletons, not store      |
| Rust native            | `tokio`, `UdpSocket`, `serialport`, `notify`             | WLED DDP port 4048; CRC-16/CCITT-FALSE framing               |
| Geometry sidecar       | Python 3.11 + FastAPI + shapely + trimesh + svgpathtools | uv-managed env at `geometry/.venv/`                          |
| Hot-reload patterns    | `notify` (Rust) → `patterns-changed` event → Blob import | Ported from Orbiter                                          |
| Persistence            | JSON `projects/*.json` with `formatVersion`              | Matches Orbiter; no SQLite unless we outgrow JSON            |
| Testing                | Vitest + pytest + `cargo check` + `tsc --noEmit`         |                                                              |
| Package managers       | npm (frontend) + uv (Python) + cargo (Rust)              | npm ships with Node; no extra install step                   |

---

## Domain model

Defined in [src/core/structure.ts](src/core/structure.ts):

- **Shape** — imported 2D motif: `{id, name, svgPath, polygon, symmetryGroup, rotationAnchor}`.
- **Tiling** — a shape + wallpaper group + global (scale, rotation, offset) + clip bounds → `PlacedTile[]`.
- **PlacedTile** — concrete polygon + centroid + area + per-tile transform (rotation picked by the lattice).
- **LedLayout** — `{positions[], wiring, pitchMm, colorOrder}`; wiring is either a single serpentine chain or a multi-output list.
- **Mapping** — `tileId → ledIndices[]` + rule (`majority-area` | `centroid`) + manual overrides.
- **Led** / **Tile** — flat per-frame views patterns consume; include the mapping so `ctx.tile(tileId, r, g, b)` writes to every LED in that cell.
- **Panel** — `tiling + ledLayout + mapping` bundled as one printable unit.
- **Project** — `{name, formatVersion, shapes[], panels[], activePatternPath}` — one JSON file.

---

## Rendering pipeline (color)

Ported from Orbiter in [src/core/colorSpace.ts](src/core/colorSpace.ts):

```
  Pattern (linear 8-bit RGB)  ──▶  brightness ──▶  gamma LUT ──▶  colorOrder
                                                                       │
                              ┌────────────────────────────────────────┤
                              ▼                                        ▼
               Float32 array for InstancedMesh               Uint8 buffer for UDP DDP
               (viewport bloom renders linearly)              (WLED sends as-is)
```

Default color order is `GRB` (WS2812), gamma 2.6, brightness 0.6. All knobs exposed in the Inspector.

---

## Dev setup

### Prereqs (Windows)

- **Node 20+** at `C:\Program Files\nodejs` — ships with `npm`, already on the standard Windows user PATH.
- **Rust** — rustup `stable-x86_64-pc-windows-msvc`. Cargo at `C:\Users\<you>\.cargo\bin\cargo.exe`.
- **MSVC Build Tools 2022** (VCTools workload). Required for Rust linking on Windows.
- **Python 3.11+** and **uv** at `%USERPROFILE%\.local\bin\uv.exe`. uv auto-installs a compatible Python on `uv sync` if you don't have one.
- **Shell** — PowerShell works (use `;` instead of `&&`). Git Bash also works but requires manually adding `%APPDATA%\npm` and `%USERPROFILE%\.local\bin` to the bash `PATH`.

Linux/macOS equivalents work too — drop the Windows-specific paths.

### One-time install

```powershell
npm install
cd geometry; uv sync; cd ..
```

### Dev loop

```powershell
npm run tauri dev                               # full desktop app (Rust spawns Python sidecar)
npm run dev                                     # pure-browser dev; sidecar must be run by hand
cd geometry; uv run tessera-api --port 8765     # run the sidecar standalone for debugging
```

### Checks

```powershell
npm run typecheck                               # tsc --noEmit
npm test                                        # vitest
cd geometry; uv run pytest; cd ..
cd src-tauri; cargo check; cd ..
```

### Common gotchas

- **Stale processes hold the port and the exe lock.** If `npm run tauri dev` fails with "sidecar did not report ready" or a Rust link error, a previous run's `tessera.exe` / `python.exe` is still alive. Recover with `taskkill /F /IM tessera.exe` then `taskkill /F /IM python.exe` (PowerShell) or the `//F //IM` form in Git Bash. Then retry.
- **Broken uv venv.** If uv ever cleans up the Python it used to create `geometry/.venv/`, the venv's `python.exe` shim starts throwing "No Python at …". Delete `geometry/.venv/` and re-run `uv sync` to rebuild against a current interpreter.
- **Python encoding.** Always `encoding="utf-8"`, `newline="\n"`. Rust shell sets `PYTHONUTF8=1` in the spawned env.
- **Windows Store Python alias.** If `python` prints "run without arguments to install…", use `py -3` instead — the alias takes precedence on a fresh Windows.
- **Icons.** Tauri's Windows resource build requires `src-tauri/icons/{32x32.png, 128x128.png, 128x128@2x.png, icon.ico, icon.icns}`. Placeholder set is checked in.

---

## Sidecar protocol

All endpoints live under `http://127.0.0.1:<port>/api/`. The port is ephemeral and handed to the webview by the Rust shell via the `get_sidecar_base` Tauri command. All routes are JSON in, JSON out; errors surface as `application/problem+json` (RFC 7807).

Request/response types are duplicated in Python (Pydantic models in [geometry/tessera/api.py](geometry/tessera/api.py)) and TypeScript (client in [src/core/api.ts](src/core/api.ts)).

| Method | Path                  | Purpose                                                       | Status |
|--------|-----------------------|---------------------------------------------------------------|--------|
| GET    | `/api/health`         | Liveness probe used by the Rust supervisor                    | done   |
| POST   | `/api/shape/import`   | SVG → shapely Polygon + symmetry hint + auto-detected pivots  | done   |
| POST   | `/api/tessellate`     | Polygon + group + transform + clip → `PlacedTile[]`           | done (p3 only) |
| POST   | `/api/map`            | Tiles + LED positions → `tileId → ledIndices[]`               | done   |
| POST   | `/api/export/stl`     | Polygon → extruded STL (solid plate, hollow ring, or capped hollow) | done |
| POST   | `/api/export/wled`    | Mapping → WLED preset JSON + ledmap + raw mapping dump        | done   |
| POST   | `/api/split`          | Panel + bed size → modules with tab+slot registration         | pending |
| POST   | `/api/export/threemf` | Module + wall height + skin thickness → 3MF file path         | pending |
| POST   | `/api/export/dxf`     | Laser-cut overlay                                             | pending |

### Startup handshake

```
Rust                          Python
─────                         ──────
pick free TCP port
spawn tessera-api --port N ──▶ uvicorn binds N
                               FastAPI lifespan prints "TESSERA_READY"
observe "TESSERA_READY" ◀────── (stdout, flushed)
cache base URL
expose via get_sidecar_base
                               └─ /api/* requests from webview
```

---

## Tessellation (current: p3 only)

`p3` is the Escher lizard group — 3-fold rotational symmetry, triangular/hex lattice. Implementation in [geometry/tessera/tessellate.py](geometry/tessera/tessellate.py).

**Algorithm**

- Hex lattice with basis `a = (L, 0)`, `b = (L/2, L·√3/2)` where `L = max(motif bbox) × latticeScale`.
- At each lattice point, place **three** copies of the motif rotated 0°/120°/240° around the motif's **anchor vertex** (which lands at the lattice point).
- This is the correct algorithm for a properly-designed p3 motif — three copies interlocking around each 3-fold centre. For an *un*-designed motif (arbitrary SVG tracing), the same placement gives overlap because the edges don't match their 120° rotations. **The algorithm is right; the motif has to be right too.**

**The Heesch construction (how to build a motif that will actually tile)**

Based on the classical deformed-hexagon method documented at [danceswithferrets.org](https://danceswithferrets.org/geekblog/?p=154):

1. Start with a regular hexagon, vertices V₀..V₅ at angles k·60° from centre.
2. Alternating vertices V₀, V₂, V₄ are **pivots** — 3-fold rotation centres in the finished tiling.
3. The six sides split into three "free/locked" pairs, one pair per pivot:
   - Around V₀: free side V₀→V₁, locked side V₅→V₀.
   - Around V₂: free side V₂→V₃, locked side V₁→V₂.
   - Around V₄: free side V₄→V₅, locked side V₃→V₄.
4. For each pair, design the **free** side as any polyline from pivot to next vertex. The **locked** side is determined by rotating the free side 120° CCW around the pivot and reversing it.
5. The resulting closed polygon is a valid p3 fundamental domain. Three of its vertices (the pivots) are the 3-fold rotation centres; assembling the tile under p3 (three copies per pivot, translated by basis vectors) gives a gap-free, overlap-free tessellation.

A reference generator lives at [geometry/scripts/generate_p3_tile.py](geometry/scripts/generate_p3_tile.py). It produces:

- `assets/shapes/p3-hex-plain.svg` — the plain regular hexagon (straight signatures, sanity check).
- `assets/shapes/p3-lizard-generated.svg` — a lizard-ish tile with parameterised bumps for head / legs / tail.

Each also gets a sidecar `.json` with the exact pivot coordinates and lattice constant, so the anchor can be set programmatically instead of by eye.

### Hand-drawn p3 tiles (auto-pivot detection)

Generated tiles are easy because the pivots are known by construction. A hand-drawn motif like the Escher lizard at [assets/shapes/lizard.svg](assets/shapes/lizard.svg) doesn't carry that metadata — the tessellator needs to *find* the three 3-fold rotation centres on the outline.

[geometry/scripts/find_pivots.py](geometry/scripts/find_pivots.py) does that in three phases:

1. **Local arc-rotation error.** At every raw SVG vertex `i`, compute `RMS_k |rotate(poly[i+k], poly[i], ±120°) − poly[i−k]|` for `k=1..K`. At a true pivot, the forward arc maps onto the backward arc → tiny error. At a random vertex, error is ~tile size.
2. **Non-max suppression + global-overlap filter.** Keep only vertices with arc-error ≤ 10% of tile span and ≤5% area overlap when the whole polygon is rotated 120° around them.
3. **Equilateral triple search.** Brute-force all 3-combinations of survivors, keep those forming an approximately equilateral triangle (≤4% side deviation), then run the actual tessellator on each candidate and pick the triple with the smallest gap/overlap.

The winning triple is written back as `data-p3-pivots="x1,y1 x2,y2 x3,y3"` on the root `<svg>`. Re-running [verify_lizard.py](geometry/scripts/verify_lizard.py) on the current lizard reports **0.0138% gap** with **98.26% central coverage** — small visible micro-gaps where the hand-drawn outline doesn't quite close, but the tile reads as a clean Escher tessellation.

The lattice constant comes from the pivot triangle itself: `|a| = |b| = 3·|r|` where `r` goes from the pivot-triangle centroid to pivot[0]. Basis `b` is `a` rotated 60° CCW. So once `data-p3-pivots` is on the SVG, the tessellator interlocks with no manual tuning.

p1 / p2 / p4 / p6 are stubbed but raise `NotImplementedError`.

---

## LED → tile mapping

Majority-area rule with centroid fallback, implemented in [geometry/tessera/mapping.py](geometry/tessera/mapping.py):

1. Build a shapely STRtree over all placed tile polygons for O(log n) candidate queries.
2. For each LED, build a small disc of `led_radius` (default `pitchMm / 2` = 5 mm for the lizard panel).
3. Query the STRtree for tiles whose bbox intersects the disc.
4. Intersect the disc with each candidate's prepared polygon; take the tile with the largest intersection area.
5. If no tile overlaps the disc, fall back to the tile whose polygon contains the LED centroid.
6. If still nothing, the LED is unmapped (viewport renders it dim gray).

This is deterministic and handles LEDs on tile boundaries sensibly.

---

## Exports

All exports are non-destructive: every click of an Export button writes into a fresh timestamped directory under `exports/<project>/<ISO-8601-stamp>/` next to the project root. Nothing is overwritten.

### STL (lizard diffuser caps)

`POST /api/export/stl` — extrudes the active shape's polygon, scaled by the current `globalTransform.scale`, into an `.stl` file. Three modes, all controlled from the Inspector's Export section:

| Mode             | Params                                         | Shape                                                                 |
|------------------|------------------------------------------------|-----------------------------------------------------------------------|
| **Solid plate**  | `height_mm` only                               | Flat extrusion of the full polygon — a decorative relief.             |
| **Hollow ring**  | `height_mm`, `wall_thickness_mm > 0`           | Lizard-outlined picture frame, open top and bottom. Stands off the LED surface. |
| **Capped hollow** | `height_mm`, `wall_thickness_mm`, `cap_thickness_mm` | Walls from z=0 to (height − cap) plus a solid lid on top. The useful shape for a diffuser cap over an LED cluster. |

Hollow modes inset the polygon by `wall_thickness_mm` using shapely's mitre-joined negative buffer; the ring is `polygon − inner`. Capped mode concatenates the ring extrusion with a full-polygon extrusion positioned at z = (height − cap). The interface between walls and cap coincides at one z plane; modern slicers (Bambu Studio, Cura, PrusaSlicer) weld it automatically so the seam is invisible in the printed part.

Thickness guards: if `wall_thickness_mm` exceeds the shape's narrowest feature the inset collapses to empty and the server returns HTTP 400 with a readable message that the Inspector surfaces inline.

Because p3 rotates one canonical motif, a single `lizard.stl` is enough to print every tile in the tessellation — user rotates copies by hand at placement time.

### WLED preset + ledmap

`POST /api/export/wled` writes three files in one call:

1. **`mapping.json`** — human-readable `{tileId: [physical_led_indices]}`, useful as reference / for downstream tooling.
2. **`ledmap1.json`** — WLED ledmap. Each lizard's LEDs are packed into a contiguous run in logical space. Upload to the ESP32 via WLED's filesystem editor (`/edit`) and enable it under Settings → LED Preferences → Ledmap.
3. **`wled-preset.json`** — one segment per lizard, referencing the contiguous ranges in the ledmapped chain. Import via Config → Presets → Restore.

Why the ledmap matters: WLED segments span only contiguous chain-index ranges, but a lizard's LEDs are typically discontiguous in the serpentine chain. Without the ledmap, a per-lizard segment would have to use `[min, max+1)` and leak into neighbouring lizards. The ledmap reorders physical LEDs so each lizard's logical range is clean — then the preset segments isolate perfectly.

Segments default to solid white at 78% brightness (`fx=0`, `bri=200`, `col=[[128,128,128],…]`); edit in the WLED UI or overwrite programmatically before saving. Segment name (`n` field) is the `tileId` for traceability.

### Physical deploy flow

1. Export STL (capped hollow), slice in Bambu Studio, print N copies (one per tile — same mold rotated by hand at placement).
2. Flash WLED to your ESP32. Upload `ledmap1.json` via `/edit`, enable it.
3. Import `wled-preset.json` via Config → Presets → Restore; activate preset 1.
4. Each lizard is now an addressable WLED segment — set its colour / effect / brightness independently, or drive with the live UDP DDP stream (pending).

---

## Repo layout

```
Lizards/                               ← local path; repo is github.com/mgarrity0/Lizard
├── README.md                          ← this file
├── CLAUDE.md                          ← operator guide (terse, end-to-end conventions)
├── package.json, pnpm-lock.yaml
├── tsconfig.json, tsconfig.node.json, vite.config.ts, index.html
│
├── src/                               ← React frontend
│   ├── components/
│   │   ├── Viewport/                  ← R3F canvas
│   │   │   ├── index.tsx              ← ortho camera, bloom, overlay
│   │   │   ├── LedDots.tsx            ← InstancedMesh of LEDs, per-LED tile color
│   │   │   ├── TileOutlines.tsx       ← line-loop outlines, stable hash color
│   │   │   ├── ShapeOutline.tsx       ← source motif outline
│   │   │   └── colors.ts              ← tileColor(id) hash → HSL
│   │   ├── ShapeLibrary.tsx           ← SVG import + shape browser
│   │   └── Inspector.tsx              ← panel, transform, tessellate/map, color pipeline
│   ├── core/                          ← framework-agnostic TS
│   │   ├── structure.ts               ← domain model (Shape/Tiling/Led/...)
│   │   ├── colorSpace.ts              ← brightness → gamma → colorOrder pipeline
│   │   ├── patternRuntime.ts          ← hot-reload ES modules via Blob URL
│   │   ├── patternApi.ts              ← meta + render(ctx, out) contract
│   │   └── api.ts                     ← typed Python sidecar client
│   ├── state/
│   │   └── store.ts                   ← zustand store (project, active ids, color config)
│   ├── App.tsx, App.css, main.tsx
│   └── vite-env.d.ts
│
├── src-tauri/                         ← Rust shell
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── icons/                         ← placeholder icon set
│   └── src/
│       ├── main.rs, lib.rs
│       ├── sidecar.rs                 ← spawn Python, observe TESSERA_READY, expose port
│       ├── patterns.rs                ← list/read/write commands for pattern files
│       └── watch.rs                   ← debounced file watcher → patterns-changed event
│
├── geometry/                          ← Python sidecar (uv project)
│   ├── pyproject.toml
│   └── tessera/
│       ├── api.py                     ← FastAPI app + routes + Pydantic models
│       ├── shapes.py                  ← SVG → shapely Polygon + symmetry guess
│       ├── tessellate.py              ← wallpaper-group tilers (p3 wired)
│       └── mapping.py                 ← LED → tile assignment (STRtree + prepared geom)
│
├── patterns/                          ← user JS patterns (hot-reloaded)
├── projects/                          ← saved project JSONs (gitignored by default)
├── assets/
│   └── shapes/                        ← shipped shape library (lizard SVG goes here)
└── docs/                              ← PROJECT_BRIEF.md (pending)
```

---

## End-to-end target: the lizard panel

Pivoted from the earlier "single multi-material 3MF per panel module" plan to **individual printed lizard caps, hand-placed** — simpler prints, easier iteration.

1. Drop `assets/shapes/lizard.svg` in place — root carries `data-p3-pivots="..."` from `find_pivots.py` so import auto-seeds the rotation anchor and lattice constant.
2. App loads SVG → shapely Polygon.
3. Inspector Panel section: set cols / rows / pitch to match your strip (default 32 × 32 @ 10 mm; auto-rebuilds positions + clip bounds).
4. Shape transform: scale the lizard so its body spans ~55 mm — each tile covers ~25–36 LEDs at 10 mm pitch.
5. **Tessellate** button fills the clip bounds with p3 lattice (3 rotated copies per lattice point).
6. **Map LEDs to tiles** assigns each LED to a lizard (majority-area + centroid fallback).
7. **Play** a pattern in the viewport to verify the mapping visually — `contrast-tiles.js` graph-colours neighbours so every lizard is distinct from its six nearest.
8. Export section:
   - **Export lizard STL** with Hollow + Cap thickness → `exports/.../lizard.stl`. One file, used for every tile (rotate by hand at placement).
   - **Export WLED preset + ledmap** → `mapping.json`, `ledmap1.json`, `wled-preset.json` (one segment per lizard, cleanly isolated via the ledmap).
9. Physical assembly:
   - Slice the STL in Bambu Studio, print N copies on black or white PETG.
   - Flash WLED to the ESP32, upload the ledmap via `/edit`, restore the preset.
   - Place each printed cap over its LED cluster — caps sit on the PCB via their hollow walls, the top cap diffuses the LEDs underneath.
10. Verify: activate preset → each lizard lights independently, graph-coloured pattern confirms the mapping.

---

## Status

| Subsystem                      | State                                                                 |
|--------------------------------|-----------------------------------------------------------------------|
| Tauri + Vite + TS strict shell | done — builds, `pnpm tauri dev` runs end to end                       |
| Python sidecar spawn + health  | done — ephemeral port, `TESSERA_READY` handshake, /api/health         |
| 3-panel UI shell               | done — ShapeLibrary / Viewport / Inspector                            |
| R3F viewport                   | done — ortho camera, InstancedMesh LEDs, tile outlines, bloom         |
| SVG import                     | done — `/api/shape/import` → polygon + symmetry hint                  |
| p3 tessellation (3 rotations per lattice point, anchor-driven) | done — `/api/tessellate` with `lattice_scale` + `anchor` |
| Inspector controls             | done — global transform, lattice spacing, anchor X/Y, tessellate/map  |
| LED layout editor              | done — cols / rows / pitch inputs, auto-rebuild grid + clip bounds    |
| LED → tile mapping             | done — `/api/map` + Map button + viewport colorize                    |
| Pattern render loop            | done — `useFrame` in LedDots.tsx, drives InstancedMesh via mapping    |
| Pattern hot-reload             | done — Rust `notify` + blob-URL dynamic import, reloads on file save  |
| Seed patterns                  | done — `solid.js`, `tile-rainbow.js`, `contrast-tiles.js` (graph-coloured) |
| p3 motif generator (Heesch)    | done — `geometry/scripts/generate_p3_tile.py` + 2 seed SVGs           |
| Hand-drawn lizard p3 import    | done — `find_pivots.py` auto-detects, 0.0138% gap, 98.26% coverage    |
| Lizard STL export              | done — `/api/export/stl`: solid / hollow ring / capped hollow modes   |
| WLED preset + ledmap           | done — `/api/export/wled`: ledmapped contiguous segments per lizard   |
| p1 / p2 / p4 / p6 tilers       | stubbed — raise `NotImplementedError`                                 |
| Wiring topology picker         | pending — chain vs multi-output UI (cols/rows is in)                  |
| WLED UDP DDP + serial          | pending — port from VolumeCube, requires flashed hardware             |
| Splitter                       | pending — not needed for single-lizard-print workflow                 |
| 3MF / DXF exporters            | pending — walls+skin multi-material, laser-cut overlays               |
| FastLED `.ino` bake            | pending — standalone microcontroller alternative to WLED              |
| `docs/PROJECT_BRIEF.md`        | pending                                                               |

---

## Next steps

What's left, in rough priority order. Each one unblocks something physical.

1. **Print + flash + light.** The pipeline is now complete through exports. Actual critical path: slice one `lizard.stl` on the A1, print N copies, flash WLED to the ESP32, upload `ledmap1.json` + `wled-preset.json`, mount the caps over the panel, verify each lizard lights independently. This validates every assumption the code makes about mm-scale, pitch, chain wiring, and colour order.
2. **WLED UDP DDP client (Rust).** Port from VolumeCube. Tauri command `start_ddp(host, port)` spawns a tokio task that drains a frame channel and pushes packets to `udp://host:4048` at 60 fps. The webview hands it the same `Uint8Array` it already builds for the viewport. *Touches:* `src-tauri/src/lib.rs`, new `src-tauri/src/ddp.rs`, `src/core/patternRuntime.ts` (frame producer). Gated on real hardware being wired up.
3. **Wiring topology picker.** Cols / rows / pitch are editable; the serpentine chain is assumed. For multi-output controllers (several parallel chains off the ESP32), add a wiring editor that lets you pick per-output start-corner + direction. Needed to generate correct WLED ledmaps for non-single-chain builds.
4. **Pattern library expansion.** `contrast-tiles.js` is the start. Targets: animated waves that *respect* the graph-colouring (so motion doesn't reintroduce neighbour-blending), audio reactive (port from Orbiter), motion reactive (IMU input → tilt-driven palette).
5. **FastLED `.ino` bake.** Compile a chosen pattern to a standalone Arduino sketch for the ESP32 — alternative to WLED. Useful if you want the panel to run without a network. Port from Orbiter.
6. **Multi-material 3MF (walls + skin).** If you end up wanting a single monolithic panel instead of discrete lizard caps: trimesh + `lib3mf` with mat-index 0 = black PETG walls, mat-index 1 = white PETG diffuser skin. Bambu AMS reads the slot index directly.
7. **Panel splitter, auxiliary STL/DXF, `docs/PROJECT_BRIEF.md`.** All pending but not on the critical path to a lit panel.

The lizard panel is the gate for declaring v1 done. Once one printed module is on the wall with WLED running a preset Tessera generated, the architecture has been validated end-to-end and the remaining work is breadth (more groups, more shapes, more outputs).

---

## Conventions (don't relitigate)

1. **Lizard-first.** Ship the Escher panel end-to-end before generalizing to other wallpaper groups or shapes.
2. **Non-reactive 60 fps hot paths.** Motion/audio/pattern state lives in module-level mutable singletons, not Zustand — avoid re-renders at frame rate.
3. **Python for geometry only.** Hardware I/O (UDP, serial) stays in Rust.
4. **Auto-snap tessellation in v1.** Scale / rotate / global XY offset only — no per-tile drag.
5. **JSON projects with `formatVersion`.** No SQLite unless we outgrow JSON.
6. **Exports are non-destructive.** Each export writes to `exports/<project>/<timestamp>/`; nothing is overwritten.

---

## Related

- [VolumeCube](https://github.com/mgarrity0/VolumeCube) — 10³ WS2815 cube. Source of the Rust WLED DDP client and serial CRC-16 framing.
- [Orbiter](https://github.com/mgarrity0/Orbiter) — 16-ft WS2815 half-dome. Source of the pattern runtime, color pipeline, 3-panel UI, audio + motion inputs, WLED preset + FastLED bake exporters.

## License

TBD.
