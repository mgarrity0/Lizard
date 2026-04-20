import { useEffect, useMemo, useRef } from 'react';
import { Color, InstancedMesh, Matrix4 } from 'three';
import type { Led, LedLayout } from '../../core/structure';
import { tileColor } from './colors';

const DOT_RADIUS_MM = 1.5;
const UNMAPPED = new Color(0.18, 0.22, 0.28);

// LED dots as an instanced mesh. Per-LED color is driven by the mapped tile
// (via `leds[i].tileId`); unmapped LEDs stay dim.
export function LedDots({ layout, leds }: { layout: LedLayout; leds: Led[] }) {
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

  useEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    for (let i = 0; i < count; i++) mesh.setMatrixAt(i, matrices[i]);
    mesh.instanceMatrix.needsUpdate = true;
    mesh.setColorAt(0, UNMAPPED);
    if (mesh.instanceColor) {
      for (let i = 0; i < count; i++) {
        const led = leds[i];
        const c = led?.tileId ? tileColor(led.tileId) : UNMAPPED;
        mesh.setColorAt(i, c);
      }
      mesh.instanceColor.needsUpdate = true;
    }
  }, [count, matrices, leds]);

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, count]}>
      <circleGeometry args={[DOT_RADIUS_MM, 12]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}
