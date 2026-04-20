# CLAUDE.md — Tessera operator guide

Short context loaded automatically every session. Full design doc lives at [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) once written.

## Who you're working with

**Matt Garrity.** Non-engineer. Designs and 3D-prints wearables and LED installations. Reads code, doesn't write it.

- Do end-to-end implementation. Never hand him step lists.
- Terse updates. One sentence per step. Don't summarize diffs.
- **Ask before committing.** Never auto-commit. Push only when he says "push."
- Ask before destructive ops (force-push, reset --hard, dropping data).
- `.env` holds real keys (gitignored). Never put real secrets in `.env.example`.
- If you spot something out of scope worth fixing, mention at end — don't silently expand.

## What Tessera is

A desktop app that takes a 2D shape (SVG/PNG/DXF/&hellip;), tessellates it across a bounded region, maps the tiles to a user-defined LED layout, and produces **all the artifacts needed to build the physical thing**:

- Multi-material 3MF (walls + skin) for Bambu A1 + AMS
- Optional spacer-frame STL, registration-jig STL, laser-cut DXF alternative
- WLED preset JSON + FastLED `.ino` bake
- Live UDP DDP preview streaming to WLED hardware

**First concrete target** is an Escher-lizard diffuser over a 32&times;32 WS2812 grid. Lizard-first shipping philosophy — generalize after the first panel is on the wall.

## Stack (locked)

- **Shell:** Tauri 2, Rust (`src-tauri/`)
- **Frontend:** React 18 + Vite 5 + TypeScript strict mode, R3F + drei + postprocessing, Zustand
- **Rust native:** `tokio`, `UdpSocket` (WLED DDP port 4048), `serialport` (CRC-16/CCITT-FALSE), `notify` (hot-reload)
- **Python sidecar:** Python 3.11 + FastAPI + shapely + trimesh + svgpathtools (optional: build123d, opencv), uv-managed at `geometry/.venv/`
- **Persistence:** JSON `projects/*.json` with `formatVersion` field
- **Testing:** Vitest + pytest + `cargo check` + `tsc --noEmit`
- **Package mgmt:** pnpm (frontend) + uv (Python) + cargo (Rust)

## Environment

- **OS:** Windows 11. Dev in bash (Git for Windows). Forward slashes. Unix shell syntax (not PowerShell).
- **Node:** `C:\Program Files\nodejs` — **not on bash PATH** by default. npm's global bin `C:\Users\Matt\AppData\Roaming\npm` *is* on PATH.
- **pnpm:** installed via `npm i -g pnpm`, at `C:\Users\Matt\AppData\Roaming\npm\pnpm.cmd`. Corepack `enable` needs admin, so we skipped it.
- **Rust:** rustup stable-x86_64-pc-windows-msvc, cargo at `C:\Users\Matt\.cargo\bin\`.
- **MSVC:** Visual Studio 2022 Build Tools (VCTools workload) at `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools`. Required for Rust linking on Windows.
- **Python:** `py -3` = 3.11.9. Use uv from `C:\Users\Matt\.local\bin\uv.exe`.
- **File I/O:** always `encoding="utf-8"`, `newline="\n"`. Set `PYTHONUTF8=1` in every spawned env (Rust shell does this).
- **Any Node subprocess call from Python or Rust**: mirror MeshHub's `_node_env()` / `_find_npm()` / `_find_npx()` helpers; use `shell=True` on Windows.

## Dev commands

```bash
# One-time setup
pnpm install
cd geometry && uv sync && cd ..

# Development
pnpm tauri dev              # full desktop app (Rust spawns Python sidecar)
pnpm dev                    # pure browser dev (sidecar must be run manually)
cd geometry && uv run tessera-api --port 8765   # run sidecar standalone

# Checks
pnpm typecheck
pnpm test
cd geometry && uv run pytest
cd src-tauri && cargo check
```

## Sidecar protocol

- Rust picks a free TCP port, spawns `python -m tessera.api --port <port>` with `PYTHONUTF8=1`
- Python prints `TESSERA_READY` to stdout from the FastAPI lifespan-startup hook once uvicorn has bound
- Rust stores the base URL, exposes it via the `get_sidecar_base` Tauri command
- React calls `http://127.0.0.1:<port>/api/*`
- Errors return RFC 7807 `application/problem+json`

## Design conventions (don't relitigate)

1. **Lizard-first.** Ship the Escher panel end-to-end before generalizing to wallpaper groups.
2. **Non-reactive 60fps hot paths.** Mirror Orbiter: motion/audio/pattern state in module-level mutable singletons, not Zustand (avoid re-renders at 60fps).
3. **Python for geometry only.** Hardware I/O (UDP, serial) stays in Rust. Don't migrate hot paths to Python just because the geometry is there.
4. **Auto-snap tessellation in v1.** No per-tile drag UI. Scale / rotate / XY offset only.
5. **JSON projects with `formatVersion`** — no SQLite unless we outgrow JSON.
6. **Exports are non-destructive.** Every export writes to `exports/<project>/<timestamp>/`; nothing is overwritten.

## Memory

Persistent memory at `C:\Users\Matt\.claude\projects\C--Users-Matt-Desktop-Lizards\memory\`. Read `MEMORY.md` at session start.
