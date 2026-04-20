import { useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrthographicCamera } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import { useStore, selectActivePanel, selectActiveShape } from '../../state/store';
import { buildLeds } from '../../core/structure';
import { LedDots } from './LedDots';
import { ShapeOutline } from './ShapeOutline';
import { TileOutlines } from './TileOutlines';

export function Viewport() {
  const panel = useStore(selectActivePanel);
  const shape = useStore(selectActiveShape);

  const leds = useMemo(
    () => buildLeds(panel.ledLayout, panel.mapping),
    [panel.ledLayout, panel.mapping],
  );

  const { minX, minY, maxX, maxY } = panel.tiling.clipBounds;
  const w = maxX - minX;
  const h = maxY - minY;
  const viewMargin = 20; // mm
  const ortho = {
    left: minX - viewMargin,
    right: maxX + viewMargin,
    top: maxY + viewMargin,
    bottom: minY - viewMargin,
    near: -100,
    far: 100,
  };

  const tileCount = panel.tiling.tiles.length;
  const mappedCount = Object.values(panel.mapping.tileLeds).reduce(
    (n, idxs) => n + idxs.length,
    0,
  );

  return (
    <div className="viewport-canvas">
      <Canvas linear flat dpr={[1, 2]}>
        <OrthographicCamera makeDefault {...ortho} position={[0, 0, 10]} />
        <color attach="background" args={['#0a0d12']} />

        {/* Panel bounds */}
        <mesh position={[(minX + maxX) / 2, (minY + maxY) / 2, -0.1]}>
          <planeGeometry args={[w, h]} />
          <meshBasicMaterial color="#111821" toneMapped={false} />
        </mesh>

        <TileOutlines tiles={panel.tiling.tiles} />
        <LedDots layout={panel.ledLayout} leds={leds} />

        {shape ? (
          <ShapeOutline
            shape={shape}
            transform={panel.tiling.globalTransform}
          />
        ) : null}

        <EffectComposer>
          <Bloom
            intensity={0.6}
            luminanceThreshold={0.2}
            luminanceSmoothing={0.2}
            mipmapBlur
          />
        </EffectComposer>
      </Canvas>
      <div className="viewport-overlay">
        <div className="viewport-info">
          {panel.ledLayout.positions.length} LEDs · {panel.ledLayout.pitchMm} mm pitch ·{' '}
          {panel.ledLayout.colorOrder}
        </div>
        {shape ? (
          <div className="viewport-info">
            shape: {shape.name} · {shape.symmetryGroup}
          </div>
        ) : (
          <div className="viewport-info dim">no shape loaded</div>
        )}
        {tileCount > 0 ? (
          <div className="viewport-info">
            {tileCount} tiles · {mappedCount} LEDs mapped
          </div>
        ) : null}
      </div>
    </div>
  );
}
