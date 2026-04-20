import { useMemo } from 'react';
import { BufferGeometry, Float32BufferAttribute } from 'three';
import type { Shape, TileTransform } from '../../core/structure';

export function ShapeOutline({
  shape,
  transform,
  anchor,
  color = '#6ae3ff',
  anchorColor = '#ffd84d',
}: {
  shape: Shape;
  transform: TileTransform;
  anchor?: [number, number];
  color?: string;
  anchorColor?: string;
}) {
  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    const pts = applyTransform(shape.polygon, transform);
    const flat: number[] = [];
    for (const [x, y] of pts) flat.push(x, y, 0.1);
    if (pts.length > 0) flat.push(pts[0][0], pts[0][1], 0.1);
    g.setAttribute('position', new Float32BufferAttribute(flat, 3));
    return g;
  }, [shape.polygon, transform]);

  const anchorGeom = useMemo(() => {
    if (!anchor) return null;
    const [ax, ay] = applyPoint(anchor, transform);
    const r = 6;
    const verts = [
      ax - r, ay, 0.3, ax + r, ay, 0.3,
      ax, ay - r, 0.3, ax, ay + r, 0.3,
    ];
    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(verts, 3));
    return g;
  }, [anchor, transform]);

  return (
    <group>
      <line>
        <primitive object={geometry} attach="geometry" />
        <lineBasicMaterial color={color} toneMapped={false} />
      </line>
      {anchorGeom ? (
        <lineSegments>
          <primitive object={anchorGeom} attach="geometry" />
          <lineBasicMaterial color={anchorColor} toneMapped={false} />
        </lineSegments>
      ) : null}
    </group>
  );
}

function applyTransform(
  polygon: Array<[number, number]>,
  t: TileTransform,
): Array<[number, number]> {
  return polygon.map((p) => applyPoint(p, t));
}

function applyPoint(
  p: [number, number],
  t: TileTransform,
): [number, number] {
  const rad = (t.rotationDeg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const s = t.scale;
  const sx = p[0] * s;
  const sy = p[1] * s;
  return [sx * cos - sy * sin + t.offset[0], sx * sin + sy * cos + t.offset[1]];
}
