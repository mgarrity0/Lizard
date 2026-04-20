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
| Package managers       | pnpm (frontend) + uv (Python) + cargo (Rust)             |                                                              |

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

- **Node 20+** at `C:\Program Files\nodejs` (not on bash PATH by default — npm's global bin `%APPDATA%\npm` is on PATH, which is what we use).
- **pnpm** — `npm i -g pnpm`. Corepack `enable` needs admin so we skipped it.
- **Rust** — rustup `stable-x86_64-pc-windows-msvc`. Cargo at `C:\Users\<you>\.cargo\bin\cargo.exe` — **not on bash PATH**; invoke by absolute path when shelling in.
- **MSVC Build Tools 2022** (VCTools workload). Required for Rust linking on Windows.
- **Python 3.11** via `py -3`. Use **uv** from `%USERPROFILE%\.local\bin\uv.exe`.
- **Git Bash** (Git for Windows). Dev in bash, not PowerShell. Forward slashes everywhere.

Linux/macOS equivalents work too — drop the Windows-specific paths.

### One-time install

```bash
pnpm install
cd geometry && uv sync && cd ..
```

### Dev loop

```bash
pnpm tauri dev                                  # full desktop app (Rust spawns Python sidecar)
pnpm dev                                        # pure-browser dev; sidecar must be run by hand
cd geometry && uv run tessera-api --port 8765   # run the sidecar standalone for debugging
```

### Checks

```bash
pnpm typecheck                                  # tsc --noEmit
pnpm test                                       # vitest
cd geometry && uv run pytest
cd src-tauri && cargo check
```

### Common gotchas

- **Windows exe lock.** After editing Rust, the running `tessera.exe` holds the binary open and the next link fails. `taskkill //F //IM tessera.exe` before re-running `cargo check` or `pnpm tauri dev`.
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
| POST   | `/api/shape/import`   | SVG → shapely Polygon + symmetry hint                         | done   |
| POST   | `/api/tessellate`     | Polygon + group + transform + clip → `PlacedTile[]`           | done (p3 only) |
| POST   | `/api/map`            | Tiles + LED positions → `tileId → ledIndices[]`               | done   |
| POST   | `/api/split`          | Panel + bed size → modules with tab+slot registration         | pending |
| POST   | `/api/export/threemf` | Module + wall height + skin thickness → 3MF file path         | pending |
| POST   | `/api/export/stl/*`   | Spacer frame, registration jig                                | pending |
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

`p3` is the Escher lizard group — 3-fold rotational symmetry, triangular/hex lattice. Three motifs per lattice cell rotated at 0°, 120°, 240°. Lattice basis:

```
a = (L, 0)
b = (L/2, L·√3/2)
```

where `L = max(bbox_w, bbox_h) × 0.5` by default. The user drives actual scale via the Inspector's global transform. Placed tiles carry the per-motif `rotation_deg` so downstream extrusion and export have everything they need. p1 / p2 / p4 / p6 are stubbed but raise `NotImplementedError` until shipping the lizard end-to-end validates the pipeline.

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

1. Drop `assets/shapes/escher-lizard.svg` in place.
2. App loads SVG → shapely Polygon → warns on gap/overlap > ε.
3. Scale slider: default lizard span ≈ 55 mm → ~25–36 LEDs/cell at 10 mm pitch.
4. LED layout editor: 32×32 grid, 10 mm pitch, wiring topology picker.
5. **Tessellate** button fills the 32×32 clip bounds with p3 lattice.
6. **Map LEDs** button assigns each LED to a tile (majority-area + centroid fallback).
7. Panel splitter breaks the full panel into ≤250×210 mm Bambu A1 modules with tab+slot registration; tile assignment preserved across splits.
8. Exports:
   - One 3MF per module (walls mat-index 0, skin mat-index 1 — Bambu AMS reads this directly).
   - `spacer-frame.stl` — 10 mm standoff around the LED PCB footprint.
   - `registration-jig.stl` — thin plate with 10 mm grid holes for assembling 4 panels.
   - `acrylic-overlay.dxf` — lizard outlines only, laser-cut alternative to printed skin.
   - `wled-preset.json` — one segment per lizard, stable IDs.
   - Optional: `panel.ino` — FastLED bake of a chosen pattern.
9. Live preview: pick a pattern from `patterns/`, press Play, UDP DDP streams at 60 fps. Viewport shows bloomed LEDs inside lizard tiles.
10. Verify: print one module, mount LEDs, flash WLED, apply preset, run a pattern → each lizard lights independently.

---

## Status

| Subsystem                      | State                                                                 |
|--------------------------------|-----------------------------------------------------------------------|
| Tauri + Vite + TS strict shell | done — builds, `pnpm tauri dev` runs end to end                       |
| Python sidecar spawn + health  | done — ephemeral port, `TESSERA_READY` handshake, /api/health         |
| 3-panel UI shell               | done — ShapeLibrary / Viewport / Inspector                            |
| R3F viewport                   | done — ortho camera, InstancedMesh LEDs, tile outlines, bloom         |
| SVG import                     | done — `/api/shape/import` → polygon + symmetry hint                  |
| p3 tessellation                | done — `/api/tessellate` + Tessellate button                          |
| LED → tile mapping             | done — `/api/map` + Map button + viewport colorize                    |
| Pattern hot-reload plumbing    | done — Rust `notify` + React blob-URL import (not yet driving LEDs)   |
| p1 / p2 / p4 / p6 tilers       | stubbed — raise `NotImplementedError`                                 |
| LED layout editor (wiring UI)  | pending                                                               |
| Pattern render loop            | pending — runtime ready, no tick wiring                               |
| WLED UDP DDP + serial          | pending — port from VolumeCube                                        |
| Splitter                       | pending                                                               |
| Exporters (3MF/STL/DXF/WLED)   | pending                                                               |
| `docs/PROJECT_BRIEF.md`        | pending                                                               |

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
