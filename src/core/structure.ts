// Tessera domain model.
//
// Coordinate convention: 2D world in millimetres. +X right, +Y up (matches
// how SVG imports are oriented once flipped for screen coords). LEDs are
// assumed coplanar for v1 but carry an optional z for future multi-layer.
//
// Patterns see a flat array of Leds plus a flat array of Tiles, and either
// write per-LED RGB directly or per-Tile RGB via the helper set on the
// context in patternRuntime.

export type ColorOrderName =
  | 'RGB' | 'RBG' | 'GRB' | 'GBR' | 'BRG' | 'BGR';

// ---------- shapes & tiling ----------

export type SymmetryGroup =
  | 'p1' | 'p2' | 'p3' | 'p4' | 'p6';

export type Shape = {
  id: string;
  name: string;
  // SVG path data (d= attribute content) for the motif outline.
  svgPath: string;
  // Canonical polygon in mm, origin-centred. Populated after import by the
  // Python sidecar.
  polygon: Array<[number, number]>;
  // Preferred wallpaper group for tessellation.
  symmetryGroup: SymmetryGroup;
  // Point around which the motif rotates (mm, in the polygon's local space).
  rotationAnchor: [number, number];
  // All 3-fold rotation centres in motif-local coords. Empty for hand-drawn
  // SVGs with no metadata; populated by generator tiles via `data-p3-pivots`.
  // The tessellator uses the pivot-to-pivot distance to set the lattice
  // constant, which is what makes tiles actually interlock.
  pivots: Array<[number, number]>;
};

export type TileTransform = {
  scale: number;
  rotationDeg: number;
  offset: [number, number];
};

export type PlacedTile = {
  id: string;
  shapeId: string;
  transform: TileTransform;
  // Concrete polygon in world-mm after transform applied.
  polygon: Array<[number, number]>;
  centroid: [number, number];
  areaMm2: number;
};

export type Tiling = {
  shapeId: string;
  group: SymmetryGroup;
  // Applied to the whole tiling after placement: uniform scale / rotate /
  // translate for global fitting.
  globalTransform: TileTransform;
  // Multiplies the auto-derived lattice constant. 1.0 = use motif bbox as-is;
  // <1 packs tiles tighter; >1 spreads them out.
  latticeScale: number;
  // Point in motif-local coords (the centered polygon) where the three
  // rotated copies pivot. For a proper p3 tile this is a specific vertex
  // of the motif — a 3-fold rotation centre. Scrub X/Y to find it by eye.
  rotationAnchor: [number, number];
  // Bounding box of the panel in world mm (LEDs that fall outside are
  // dropped).
  clipBounds: { minX: number; minY: number; maxX: number; maxY: number };
  tiles: PlacedTile[];
};

// ---------- LEDs & wiring ----------

export type ChainWiring = {
  kind: 'chain';
  // Flat indices into LedLayout.positions, in the physical serpentine order.
  order: number[];
};

export type MultiOutputWiring = {
  kind: 'multi-output';
  // Multiple parallel chains (one per controller output). Each chain is a
  // list of flat indices into LedLayout.positions.
  outputs: number[][];
};

export type Wiring = ChainWiring | MultiOutputWiring;

export type LedLayout = {
  // Flat list of LED positions in world-mm. Optional z for future stacked
  // diffusers.
  positions: Array<[number, number] | [number, number, number]>;
  wiring: Wiring;
  // Physical LED pitch in mm (used only for layout UI; the positions are
  // authoritative).
  pitchMm: number;
  colorOrder: ColorOrderName;
};

// Per-LED record as seen by patterns. `i` is the flat index into the pattern
// output buffer (out[i*3+0..2] = RGB).
export type Led = {
  i: number;
  x: number;
  y: number;
  z: number;
  // Tile this LED was mapped into, or null for LEDs outside any tile.
  tileId: string | null;
};

// Per-tile record as seen by patterns.
export type Tile = {
  id: string;
  shapeId: string;
  centroid: [number, number];
  areaMm2: number;
  // LED indices (into the flat Led array) mapped to this tile.
  ledIndices: number[];
};

// ---------- panel & mapping ----------

export type Mapping = {
  // tileId -> led indices; mirrors Tile.ledIndices but authoritative.
  tileLeds: Record<string, number[]>;
  rule: 'majority-area' | 'centroid';
  // Manual overrides keyed by led index.
  manualOverrides: Record<number, string>;
};

export type Panel = {
  id: string;
  tiling: Tiling;
  ledLayout: LedLayout;
  mapping: Mapping;
};

export type Project = {
  name: string;
  formatVersion: 1;
  shapes: Shape[];
  panels: Panel[];
  activePatternPath: string | null;
};

// ---------- derivations ----------

export function buildLeds(layout: LedLayout, mapping: Mapping): Led[] {
  const overrides = mapping.manualOverrides;
  const tileByLed: Record<number, string> = {};
  for (const [tileId, ledIdxs] of Object.entries(mapping.tileLeds)) {
    for (const idx of ledIdxs) tileByLed[idx] = tileId;
  }
  const leds: Led[] = [];
  for (let i = 0; i < layout.positions.length; i++) {
    const p = layout.positions[i];
    leds.push({
      i,
      x: p[0],
      y: p[1],
      z: p.length > 2 ? (p as [number, number, number])[2] : 0,
      tileId: overrides[i] ?? tileByLed[i] ?? null,
    });
  }
  return leds;
}

export function buildTiles(tiling: Tiling, mapping: Mapping): Tile[] {
  return tiling.tiles.map((placed) => ({
    id: placed.id,
    shapeId: placed.shapeId,
    centroid: placed.centroid,
    areaMm2: placed.areaMm2,
    ledIndices: mapping.tileLeds[placed.id] ?? [],
  }));
}

export function totalLedCount(layout: LedLayout): number {
  return layout.positions.length;
}

// ---------- defaults for the lizard panel ----------

// 32 x 32 @ 10mm pitch = a 320mm square centred on origin.
export function default32x32Grid(pitchMm = 10): LedLayout {
  const n = 32;
  const positions: Array<[number, number]> = [];
  const half = ((n - 1) * pitchMm) / 2;
  // Serpentine chain: row 0 left-to-right, row 1 right-to-left, etc.
  const order: number[] = [];
  for (let row = 0; row < n; row++) {
    for (let col = 0; col < n; col++) {
      positions.push([col * pitchMm - half, row * pitchMm - half]);
    }
  }
  for (let row = 0; row < n; row++) {
    const base = row * n;
    if (row % 2 === 0) {
      for (let col = 0; col < n; col++) order.push(base + col);
    } else {
      for (let col = n - 1; col >= 0; col--) order.push(base + col);
    }
  }
  return {
    positions,
    wiring: { kind: 'chain', order },
    pitchMm,
    colorOrder: 'GRB',
  };
}

export function emptyMapping(): Mapping {
  return { tileLeds: {}, rule: 'majority-area', manualOverrides: {} };
}
