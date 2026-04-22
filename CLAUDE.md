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
- **Package mgmt:** npm (frontend) + uv (Python) + cargo (Rust)

## Environment

- **OS:** Windows 11. Default shell is PowerShell (use `;` instead of `&&`). Git Bash works but requires adding `%APPDATA%\npm` and `%USERPROFILE%\.local\bin` to `PATH` manually.
- **Node:** `C:\Program Files\nodejs` — on the standard Windows user PATH, ships with `npm`.
- **Rust:** rustup stable-x86_64-pc-windows-msvc, cargo at `C:\Users\<you>\.cargo\bin\`.
- **MSVC:** Visual Studio 2022 Build Tools (VCTools workload) at `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools`. Required for Rust linking on Windows.
- **Python + uv:** `uv` at `%USERPROFILE%\.local\bin\uv.exe`. `uv sync` auto-installs a compatible CPython if one isn't already usable.
- **File I/O:** always `encoding="utf-8"`, `newline="\n"`. Set `PYTHONUTF8=1` in every spawned env (Rust shell does this).

## Dev commands

```powershell
# One-time setup
npm install
cd geometry; uv sync; cd ..

# Development
npm run tauri dev           # full desktop app (Rust spawns Python sidecar)
npm run dev                 # pure browser dev (sidecar must be run manually)
cd geometry; uv run tessera-api --port 8765   # run sidecar standalone

# Checks
npm run typecheck
npm test
cd geometry; uv run pytest; cd ..
cd src-tauri; cargo check; cd ..
```

### Recovery

If `npm run tauri dev` fails with "sidecar did not report ready" or a Rust link error, a zombie from a previous run is holding the port or the exe lock:

```powershell
taskkill /F /IM tessera.exe ; taskkill /F /IM python.exe
```

If uv ever warns about a venv linked to a non-existent interpreter, delete `geometry/.venv/` and re-run `uv sync`.

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

Persistent memory at `C:\Users\<you>\.claude\projects\C--Users-<you>-Desktop-Claude-Lizard\memory\`. Read `MEMORY.md` at session start.
