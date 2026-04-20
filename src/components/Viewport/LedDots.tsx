import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Color, InstancedMesh, Matrix4 } from 'three';
import type { Led, LedLayout, Tile } from '../../core/structure';
import type { PatternModule, RenderContext } from '../../core/patternApi';
import { bakeFrameToLinearFloats, type ColorConfig } from '../../core/colorSpace';
import { tileColor } from './colors';

const DOT_RADIUS_MM = 1.5;
const UNMAPPED = new Color(0.18, 0.22, 0.28);

// Instanced LED dots. Two rendering modes:
// - Idle (no pattern / not playing): per-LED colour is the stable hash of its
//   tile id so the mapping is legible at a glance.
// - Playing: `useFrame` runs the pattern render + color pipeline every tick
//   and writes the Float32 result directly into the instanceColor buffer.
export function LedDots({
  layout,
  leds,
  tiles,
  patternModule,
  playing,
  colorConfig,
}: {
  layout: LedLayout;
  leds: Led[];
  tiles: Tile[];
  patternModule: PatternModule | null;
  playing: boolean;
  colorConfig: ColorConfig;
}) {
  const ref = useRef<InstancedMesh>(null);
  const count = layout.positions.length;

  const matrices = useMemo(() => {
    const m = new Matrix4();
    const arr: Matrix4[] = [];
    for (const p of layout.positions) {
      m.identity();
      const z = p.length > 2 ? (p as [number, number, number])[2] : 0;
      m.setPosition(p[0], p[1], z);
      arr.push(m.clone());
    }
    return arr;
  }, [layout.positions]);

  // Per-tile → LED indices map, for ctx.tile(id, r, g, b).
  const tileToLeds = useMemo(() => {
    const m = new Map<string, number[]>();
    for (const t of tiles) m.set(t.id, t.ledIndices);
    return m;
  }, [tiles]);

  // Frame buffers. Size tracks `count`; re-allocated only when count changes.
  const outRef = useRef<Uint8ClampedArray>(new Uint8ClampedArray(count * 3));
  const colorsRef = useRef<Float32Array>(new Float32Array(count * 3));
  useEffect(() => {
    outRef.current = new Uint8ClampedArray(count * 3);
    colorsRef.current = new Float32Array(count * 3);
  }, [count]);

  // Clock. Resets whenever a pattern is loaded or playback toggles on.
  const clockRef = useRef({ start: 0, lastTick: 0, frame: 0 });
  useEffect(() => {
    const now = performance.now() / 1000;
    clockRef.current = { start: now, lastTick: now, frame: 0 };
  }, [patternModule, playing]);

  // Matrix placement: write once per position change.
  useEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    for (let i = 0; i < count; i++) mesh.setMatrixAt(i, matrices[i]);
    mesh.instanceMatrix.needsUpdate = true;
    // Ensure instanceColor exists so useFrame can write into it.
    mesh.setColorAt(0, UNMAPPED);
  }, [count, matrices]);

  // Idle colouring: whenever we are NOT playing, paint each LED by its tile
  // hash. Runs on any leds/tiles/playing change, NOT every frame.
  useEffect(() => {
    if (playing && patternModule) return;
    const mesh = ref.current;
    if (!mesh || !mesh.instanceColor) return;
    for (let i = 0; i < count; i++) {
      const led = leds[i];
      const c = led?.tileId ? tileColor(led.tileId) : UNMAPPED;
      mesh.setColorAt(i, c);
    }
    mesh.instanceColor.needsUpdate = true;
  }, [count, leds, playing, patternModule]);

  useFrame(() => {
    if (!playing || !patternModule || count === 0) return;
    const mesh = ref.current;
    if (!mesh || !mesh.instanceColor) return;

    const out = outRef.current;
    const colors = colorsRef.current;
    const now = performance.now() / 1000;
    const time = now - clockRef.current.start;
    const dt = now - clockRef.current.lastTick;
    clockRef.current.lastTick = now;
    clockRef.current.frame += 1;

    const ctx: RenderContext = {
      time,
      dt,
      frame: clockRef.current.frame,
      leds,
      tiles,
      ledCount: count,
      tile: (tileId, r, g, b) => {
        const idxs = tileToLeds.get(tileId);
        if (!idxs) return;
        for (const idx of idxs) {
          const j = idx * 3;
          out[j] = r;
          out[j + 1] = g;
          out[j + 2] = b;
        }
      },
    };

    try {
      patternModule.render(ctx, out);
    } catch (e) {
      console.error('pattern render threw', e);
      return;
    }

    bakeFrameToLinearFloats(out, colors, colorConfig);

    const buf = mesh.instanceColor.array as Float32Array;
    buf.set(colors);
    mesh.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, count]}>
      <circleGeometry args={[DOT_RADIUS_MM, 12]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}
