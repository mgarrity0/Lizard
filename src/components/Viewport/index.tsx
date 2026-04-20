import { useEffect, useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrthographicCamera } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import { useStore, selectActivePanel, selectActiveShape } from '../../state/store';
import { buildLeds, buildTiles } from '../../core/structure';
import type { PatternModule } from '../../core/patternApi';
import {
  loadPattern,
  onPatternsChanged,
  startWatching,
  getProjectRoot,
  patternsDirFor,
} from '../../core/patternRuntime';
import { LedDots } from './LedDots';
import { ShapeOutline } from './ShapeOutline';
import { TileOutlines } from './TileOutlines';

export function Viewport() {
  const panel = useStore(selectActivePanel);
  const shape = useStore(selectActiveShape);
  const activePatternPath = useStore((s) => s.project.activePatternPath);
  const playing = useStore((s) => s.playing);
  const colorConfig = useStore((s) => s.colorConfig);

  const leds = useMemo(
    () => buildLeds(panel.ledLayout, panel.mapping),
    [panel.ledLayout, panel.mapping],
  );
  const tiles = useMemo(
    () => buildTiles(panel.tiling, panel.mapping),
    [panel.tiling, panel.mapping],
  );

  const [patternModule, setPatternModule] = useState<PatternModule | null>(null);
  const [patternError, setPatternError] = useState<string | null>(null);

  // Start the Rust-side patterns-dir watcher once on mount. Safe to call
  // repeatedly — `ensure` on the Rust side is idempotent.
  useEffect(() => {
    (async () => {
      try {
        const root = await getProjectRoot();
        await startWatching(patternsDirFor(root));
      } catch (e) {
        console.warn('startWatching failed (non-Tauri dev?)', e);
      }
    })();
  }, []);

  // Load the active pattern when its name changes.
  useEffect(() => {
    let cancelled = false;
    if (!activePatternPath) {
      setPatternModule(null);
      setPatternError(null);
      return;
    }
    (async () => {
      const res = await loadPattern(activePatternPath);
      if (cancelled) return;
      if (res.ok) {
        // Run setup once.
        try {
          res.module.setup?.({ leds, tiles, ledCount: leds.length });
        } catch (e) {
          console.error('pattern setup threw', e);
        }
        setPatternModule(res.module);
        setPatternError(null);
      } else {
        setPatternModule(null);
        setPatternError(res.error);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Intentionally do not rerun on leds/tiles change — setup() runs on load,
    // render() gets fresh leds/tiles every frame via the ctx.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePatternPath]);

  // Hot-reload: when the active pattern file changes on disk, re-import it.
  useEffect(() => {
    if (!activePatternPath) return;
    let unsub: (() => void) | null = null;
    (async () => {
      unsub = await onPatternsChanged(async (paths) => {
        const touched = paths.some((p) => p.endsWith(activePatternPath));
        if (!touched) return;
        const res = await loadPattern(activePatternPath);
        if (res.ok) {
          setPatternModule(res.module);
          setPatternError(null);
        } else {
          setPatternError(res.error);
        }
      });
    })();
    return () => {
      if (unsub) unsub();
    };
  }, [activePatternPath]);

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
        <LedDots
          layout={panel.ledLayout}
          leds={leds}
          tiles={tiles}
          patternModule={patternModule}
          playing={playing}
          colorConfig={colorConfig}
        />

        {shape ? (
          <ShapeOutline
            shape={shape}
            transform={panel.tiling.globalTransform}
            anchor={panel.tiling.rotationAnchor}
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
        {activePatternPath ? (
          <div className="viewport-info">
            pattern: {activePatternPath} · {playing ? 'playing' : 'paused'}
          </div>
        ) : null}
        {patternError ? (
          <div className="viewport-info error">{patternError}</div>
        ) : null}
      </div>
    </div>
  );
}
