/**
 * Tessera pattern — contrast-aware tiles.
 *
 * Greedy graph-coloring so adjacent lizards never share a hue. Each tile's
 * nearest 6 centroids are its "neighbours"; Welsh-Powell orders tiles by
 * degree and assigns the lowest unused color. We then rotate the whole
 * palette over time so the panel still feels animated, but each lizard
 * remains clearly distinct from every lizard touching it.
 *
 * On a regular p3 tiling this lands at 4-6 classes, matching the four-color
 * theorem bound for planar graphs plus a little slack from KNN false
 * positives. More classes = more contrast, which is what we want.
 */

export const meta = {
  name: "Contrast tiles",
  description: "Neighbouring tiles always get different colors; palette rotates over time.",
};

const K = 6;       // nearest centroids treated as adjacency
const SPEED = 15;  // palette rotation deg/sec
const SAT = 0.85;
const VAL = 1.0;

let cache = null;  // { sig, color[], numClasses }

function buildAdjacency(tiles) {
  const n = tiles.length;
  const adj = Array.from({ length: n }, () => new Set());
  for (let i = 0; i < n; i++) {
    const [xi, yi] = tiles[i].centroid;
    const dists = [];
    for (let j = 0; j < n; j++) {
      if (j === i) continue;
      const [xj, yj] = tiles[j].centroid;
      dists.push([Math.hypot(xi - xj, yi - yj), j]);
    }
    dists.sort((a, b) => a[0] - b[0]);
    const take = Math.min(K, dists.length);
    for (let r = 0; r < take; r++) {
      const j = dists[r][1];
      adj[i].add(j);
      adj[j].add(i);
    }
  }
  return adj.map(s => [...s]);
}

function greedyColor(adj) {
  const n = adj.length;
  const color = new Array(n).fill(-1);
  const order = Array.from({ length: n }, (_, i) => i)
    .sort((a, b) => adj[b].length - adj[a].length);
  let maxColor = -1;
  for (const i of order) {
    const used = new Set();
    for (const j of adj[i]) if (color[j] !== -1) used.add(color[j]);
    let c = 0;
    while (used.has(c)) c++;
    color[i] = c;
    if (c > maxColor) maxColor = c;
  }
  return { color, numClasses: maxColor + 1 };
}

function ensureCache(tiles) {
  // Cache key that invalidates when tile set changes (count + first/last id)
  const sig = `${tiles.length}|${tiles[0]?.id ?? ""}|${tiles[tiles.length - 1]?.id ?? ""}`;
  if (cache && cache.sig === sig) return cache;
  const adj = buildAdjacency(tiles);
  const { color, numClasses } = greedyColor(adj);
  cache = { sig, color, numClasses };
  return cache;
}

export function render(ctx, out) {
  for (let i = 0; i < out.length; i++) out[i] = 0;
  if (ctx.tiles.length === 0) return;

  const { color, numClasses } = ensureCache(ctx.tiles);
  const rotation = ctx.time * SPEED;
  const step = 360 / numClasses;

  for (let i = 0; i < ctx.tiles.length; i++) {
    const tile = ctx.tiles[i];
    const hue = (color[i] * step + rotation) % 360;
    const [r, g, b] = hsvToRgb(hue, SAT, VAL);
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
