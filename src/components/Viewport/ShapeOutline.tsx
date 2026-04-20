import { useMemo } from 'react';
import { BufferGeometry, Float32BufferAttribute } from 'three';
import type { Shape, TileTransform } from '../../core/structure';

export function ShapeOutline({
  shape,
  transform,
  color = '#6ae3ff',
}: {
  shape: Shape;
  transform: TileTransform;
  color?: string;
}) {
  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    const pts = applyTransform(shape.polygon, transform);
    // Close the loop
    const flat: number[] = [];
    for (const [x, y] of pts) flat.push(x, y, 0.1);
    if (pts.length > 0) {
      flat.push(pts[0][0], pts[0][1], 0.1);
    }
    g.setAttribute('position', new Float32BufferAttribute(flat, 3));
    return g;
  }, [shape.polygon, transform]);

  return (
    <line>
      <primitive object={geometry} attach="geometry" />
      <lineBasicMaterial color={color} linewidth={1} toneMapped={false} />
    </line>
  );
}

function applyTransform(
  polygon: Array<[number, number]>,
  t: TileTransform,
): Array<[number, number]> {
  const rad = (t.rotationDeg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const s = t.scale;
  return polygon.map(([x, y]) => {
    const sx = x * s;
    const sy = y * s;
    return [sx * cos - sy * sin + t.offset[0], sx * sin + sy * cos + t.offset[1]];
  });
}
