"""Tessera geometry sidecar — FastAPI app.

The Rust shell's supervisor waits for ``TESSERA_READY`` on stdout before
considering the sidecar live. We emit that marker from the FastAPI lifespan
startup hook, after uvicorn has bound the port.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from tessera import __version__
from tessera.mapping import PlacedTileRef, map_leds_to_tiles
from tessera.shapes import decode_data_source, import_shape_from_svg
from tessera.tessellate import ClipBounds, Transform2D, tessellate


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Startup: signal the Rust supervisor that we're live.
    print("TESSERA_READY", flush=True)
    sys.stdout.flush()
    yield
    # Shutdown: nothing to do for now.


class Health(BaseModel):
    status: str
    version: str


class ShapeImportRequest(BaseModel):
    source: str = Field(..., description="svg | png | dxf")
    data: str = Field(..., description="base64-encoded source bytes")


class ShapeImportResponse(BaseModel):
    polygon: list[tuple[float, float]]
    width: float
    height: float
    symmetry_hint: str
    rotation_anchor: tuple[float, float]


class ApiTransform(BaseModel):
    scale: float = 1.0
    rotation_deg: float = 0.0
    offset: tuple[float, float] = (0.0, 0.0)


class ApiClipBounds(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float


class TessellateRequest(BaseModel):
    polygon: list[tuple[float, float]]
    group: str = "p3"
    global_transform: ApiTransform = ApiTransform()
    clip_bounds: ApiClipBounds
    lattice_scale: float = 1.0
    anchor: tuple[float, float] = (0.0, 0.0)


class ApiPlacedTile(BaseModel):
    tile_id: str
    polygon: list[tuple[float, float]]
    centroid: tuple[float, float]
    area_mm2: float
    rotation_deg: float


class TessellateResponse(BaseModel):
    tiles: list[ApiPlacedTile]


class ApiTileRef(BaseModel):
    id: str
    polygon: list[tuple[float, float]]


class MapRequest(BaseModel):
    tiles: list[ApiTileRef]
    led_positions: list[tuple[float, float]]
    rule: str = "majority-area"
    led_radius: float = 5.0


class MapResponse(BaseModel):
    mapping: dict[str, list[int]]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tessera geometry sidecar",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS: allow everything for a local-only service; Tauri webview origin
    # varies by platform (tauri://localhost vs https://tauri.localhost).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        return Health(status="ok", version=__version__)

    @app.post("/api/shape/import", response_model=ShapeImportResponse)
    def shape_import(req: ShapeImportRequest) -> ShapeImportResponse:
        try:
            raw = decode_data_source(req.source, req.data)
        except NotImplementedError as e:
            raise HTTPException(status_code=501, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"decode: {e}") from e

        if req.source == "svg":
            shape = import_shape_from_svg(raw)
        else:  # pragma: no cover — guarded above
            raise HTTPException(status_code=501, detail=f"{req.source} not implemented")

        return ShapeImportResponse(
            polygon=shape.polygon,
            width=shape.width,
            height=shape.height,
            symmetry_hint=shape.symmetry_hint,
            rotation_anchor=shape.rotation_anchor,
        )

    @app.post("/api/tessellate", response_model=TessellateResponse)
    def tessellate_route(req: TessellateRequest) -> TessellateResponse:
        try:
            placed = tessellate(
                polygon=req.polygon,
                group=req.group,  # type: ignore[arg-type]
                global_transform=Transform2D(
                    scale=req.global_transform.scale,
                    rotation_deg=req.global_transform.rotation_deg,
                    offset=req.global_transform.offset,
                ),
                clip_bounds=ClipBounds(
                    min_x=req.clip_bounds.min_x,
                    min_y=req.clip_bounds.min_y,
                    max_x=req.clip_bounds.max_x,
                    max_y=req.clip_bounds.max_y,
                ),
                lattice_scale=req.lattice_scale,
                anchor=req.anchor,
            )
        except NotImplementedError as e:
            raise HTTPException(status_code=501, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        return TessellateResponse(
            tiles=[
                ApiPlacedTile(
                    tile_id=p.tile_id,
                    polygon=p.polygon,
                    centroid=p.centroid,
                    area_mm2=p.area_mm2,
                    rotation_deg=p.rotation_deg,
                )
                for p in placed
            ]
        )

    @app.post("/api/map", response_model=MapResponse)
    def map_route(req: MapRequest) -> MapResponse:
        refs = [PlacedTileRef(id=t.id, polygon=t.polygon) for t in req.tiles]
        mapping = map_leds_to_tiles(
            refs,
            req.led_positions,
            rule=req.rule,  # type: ignore[arg-type]
            led_radius=req.led_radius,
        )
        return MapResponse(mapping=mapping)

    return app


app = create_app()


def cli_main() -> None:
    parser = argparse.ArgumentParser(prog="tessera-api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=False,
    )


if __name__ == "__main__":
    cli_main()
