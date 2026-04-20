import { useMemo } from 'react';
import { BufferGeometry, Float32BufferAttribute } from 'three';
import type { PlacedTile } from '../../core/structure';
import { tileColor } from './colors';

// Render all placed tile polygons as line loops, coloured by a stable hash
// of the tile id so you can see which tile is which.
export function TileOutlines({ tiles }: { tiles: PlacedTile[] }) {
  const items = useMemo(() => {
    return tiles.map((t) => {
      const g = new BufferGeometry();
      const flat: number[] = [];
      for (const [x, y] of t.polygon) flat.push(x, y, 0.05);
      if (t.polygon.length > 0) {
        flat.push(t.polygon[0][0], t.polygon[0][1], 0.05);
      }
      g.setAttribute('position', new Float32BufferAttribute(flat, 3));
      return { id: t.id, geometry: g, color: tileColor(t.id) };
    });
  }, [tiles]);

  return (
    <group>
      {items.map(({ id, geometry, color }) => (
        <line key={id}>
          <primitive object={geometry} attach="geometry" />
          <lineBasicMaterial color={color} toneMapped={false} />
        </line>
      ))}
    </group>
  );
}
