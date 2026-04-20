// Public API a pattern file on disk sees.
//
// A pattern is a plain ES module — anything importable by a browser. The
// canonical shape is:
//
//   export const meta = { name: 'solid', description: 'one color' };
//   export function setup(ctx) { /* optional, called once on load */ }
//   export function render(ctx, out) {
//     // out is a Uint8ClampedArray of length ctx.leds.length * 3
//     // out[i*3+0..2] = [r, g, b] in linear 8-bit
//   }
//
// Patterns get per-LED access via ctx.leds and per-tile access via ctx.tiles.
// ctx.tile(tileId, r, g, b) is a helper that writes a colour to every LED
// inside a tile; see patternRuntime for how it is installed.

import type { Led, Tile } from './structure';

export type RenderContext = {
  time: number;      // seconds since activation
  dt: number;        // seconds since previous frame
  frame: number;     // monotonic frame counter
  leds: Led[];
  tiles: Tile[];
  ledCount: number;
  // Set by the runtime: fills every LED inside a tile with the given 8-bit
  // RGB. No-op if the tile id is unknown.
  tile: (tileId: string, r: number, g: number, b: number) => void;
};

export type SetupContext = {
  leds: Led[];
  tiles: Tile[];
  ledCount: number;
};

export type PatternMeta = {
  name?: string;
  description?: string;
  author?: string;
};

export type PatternModule = {
  meta?: PatternMeta;
  setup?: (ctx: SetupContext) => void;
  render: (ctx: RenderContext, out: Uint8ClampedArray) => void;
};

export function isPatternModule(mod: unknown): mod is PatternModule {
  return !!mod && typeof (mod as PatternModule).render === 'function';
}
