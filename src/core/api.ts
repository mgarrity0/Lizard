/**
 * Python sidecar HTTP client.
 *
 * In dev and packaged builds, the Rust shell spawns the Python FastAPI sidecar
 * on an ephemeral port and reports the URL via the `get_sidecar_base` Tauri
 * command. In pure-browser dev (no Tauri), we fall back to the env var
 * VITE_SIDECAR_BASE or the default 127.0.0.1:8765.
 */

type InvokeFn = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;

let cachedBase: string | null = null;

async function getTauriInvoke(): Promise<InvokeFn | null> {
  // `__TAURI_INTERNALS__` is injected by Tauri into the webview.
  if (typeof window === "undefined") return null;
  const w = window as unknown as { __TAURI_INTERNALS__?: unknown };
  if (!w.__TAURI_INTERNALS__) return null;
  const mod = await import("@tauri-apps/api/core");
  return mod.invoke as InvokeFn;
}

export async function getSidecarBase(): Promise<string> {
  if (cachedBase) return cachedBase;
  const invoke = await getTauriInvoke();
  if (invoke) {
    const url = (await invoke("get_sidecar_base")) as string;
    cachedBase = url;
    return url;
  }
  const fallback = import.meta.env.VITE_SIDECAR_BASE ?? "http://127.0.0.1:8765";
  cachedBase = fallback;
  return fallback;
}

export async function ping(): Promise<boolean> {
  try {
    const base = await getSidecarBase();
    const r = await fetch(`${base}/api/health`);
    if (!r.ok) return false;
    const j = (await r.json()) as { status?: string };
    return j.status === "ok";
  } catch {
    return false;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const base = await getSidecarBase();
  const r = await fetch(`${base}${path}`);
  if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`);
  return (await r.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const base = await getSidecarBase();
  const r = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = "";
    try {
      detail = await r.text();
    } catch {
      /* ignore */
    }
    throw new Error(`POST ${path} -> ${r.status} ${detail}`.trim());
  }
  return (await r.json()) as T;
}

// ---------- domain helpers ----------

export type ShapeImportResponse = {
  polygon: Array<[number, number]>;
  width: number;
  height: number;
  symmetry_hint: "p1" | "p2" | "p3" | "p4" | "p6";
  rotation_anchor: [number, number];
};

export async function importSvgShape(
  bytes: ArrayBuffer | Uint8Array,
): Promise<ShapeImportResponse> {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  // btoa expects binary string; build it in chunks to avoid stack overflow
  // on very large SVGs.
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < u8.length; i += chunk) {
    bin += String.fromCharCode.apply(null, Array.from(u8.subarray(i, i + chunk)));
  }
  const data = btoa(bin);
  return await apiPost<ShapeImportResponse>("/api/shape/import", {
    source: "svg",
    data,
  });
}

export type TessellateRequest = {
  polygon: Array<[number, number]>;
  group: "p1" | "p2" | "p3" | "p4" | "p6";
  global_transform: {
    scale: number;
    rotation_deg: number;
    offset: [number, number];
  };
  clip_bounds: { min_x: number; min_y: number; max_x: number; max_y: number };
};

export type TessellateResponse = {
  tiles: Array<{
    tile_id: string;
    polygon: Array<[number, number]>;
    centroid: [number, number];
    area_mm2: number;
    rotation_deg: number;
  }>;
};

export async function tessellate(req: TessellateRequest): Promise<TessellateResponse> {
  return await apiPost<TessellateResponse>("/api/tessellate", req);
}

export type MapRequest = {
  tiles: Array<{ id: string; polygon: Array<[number, number]> }>;
  led_positions: Array<[number, number]>;
  rule?: "majority-area" | "centroid";
  led_radius?: number;
};

export type MapResponse = {
  mapping: Record<string, number[]>;
};

export async function mapLedsToTiles(req: MapRequest): Promise<MapResponse> {
  return await apiPost<MapResponse>("/api/map", req);
}
