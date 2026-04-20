/**
 * Tessera pattern — solid color per tile.
 *
 * Patterns are plain ES modules with `meta` + `render(ctx, out)`. The runtime
 * hot-reloads them via the notify crate on the Rust side.
 *
 * ctx: {
 *   time: number         seconds since start
 *   frame: number        monotonic frame counter
 *   tiles: Tile[]        array of { id, centroid: [x,y], bounds, area }
 *   leds:  Led[]         array of { id, x, y, tileId }
 * }
 * out: Uint8Array of length leds.length * 3 (RGB)
 */

export const meta = {
  name: "Solid",
  description: "All tiles one colour (hue slowly shifts).",
};

export function render(ctx, out) {
  const hue = (ctx.time * 20) % 360;
  const [r, g, b] = hsvToRgb(hue, 0.6, 1.0);
  for (let i = 0; i < ctx.leds.length; i++) {
    const j = i * 3;
    out[j] = r;
    out[j + 1] = g;
    out[j + 2] = b;
  }
}

function hsvToRgb(h, s, v) {
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let r = 0,
    g = 0,
    b = 0;
  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  return [
    Math.round((r + m) * 255),
    Math.round((g + m) * 255),
    Math.round((b + m) * 255),
  ];
}
