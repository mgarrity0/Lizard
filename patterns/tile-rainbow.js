/**
 * Tessera pattern — per-tile rainbow.
 *
 * Each tile cycles through the hue spectrum, with a phase offset based on
 * its centroid position. This makes the LED-to-tile mapping obvious: every
 * LED inside one lizard has the same color and they all shift together.
 */

export const meta = {
  name: "Tile rainbow",
  description: "Each tile cycles through hue; phase shifts by tile position.",
};

export function render(ctx, out) {
  // Clear unmapped LEDs to black.
  for (let i = 0; i < out.length; i++) out[i] = 0;

  const speed = 30; // deg/sec
  for (const tile of ctx.tiles) {
    const [cx, cy] = tile.centroid;
    // Use centroid distance as the phase offset so neighbouring tiles are
    // close in hue — pattern reads as a sweeping gradient over the panel.
    const dist = Math.sqrt(cx * cx + cy * cy);
    const hue = (ctx.time * speed + dist * 1.5) % 360;
    const [r, g, b] = hsvToRgb(hue, 0.75, 1.0);
    ctx.tile(tile.id, r, g, b);
  }
}

function hsvToRgb(h, s, v) {
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let r = 0, g = 0, b = 0;
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
