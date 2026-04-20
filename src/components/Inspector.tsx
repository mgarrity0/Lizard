import { useEffect, useState } from 'react';
import { useStore, selectActivePanel, selectActiveShape } from '../state/store';
import type { ColorOrderName, PlacedTile, Mapping } from '../core/structure';
import { tessellate, mapLedsToTiles } from '../core/api';
import { listPatterns, onPatternsChanged } from '../core/patternRuntime';

const COLOR_ORDERS: ColorOrderName[] = ['RGB', 'RBG', 'GRB', 'GBR', 'BRG', 'BGR'];

export function Inspector() {
  const panel = useStore(selectActivePanel);
  const shape = useStore(selectActiveShape);
  const updatePanel = useStore((s) => s.updatePanel);
  const colorConfig = useStore((s) => s.colorConfig);
  const setColorConfig = useStore((s) => s.setColorConfig);
  const activePatternPath = useStore((s) => s.project.activePatternPath);
  const setActivePattern = useStore((s) => s.setActivePattern);
  const playing = useStore((s) => s.playing);
  const setPlaying = useStore((s) => s.setPlaying);

  const [busy, setBusy] = useState<'idle' | 'tessellate' | 'map'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [patternNames, setPatternNames] = useState<string[]>([]);

  // Populate pattern list on mount and whenever the watcher fires.
  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const names = await listPatterns();
      if (!cancelled) setPatternNames(names);
    };
    refresh();
    let unsub: (() => void) | null = null;
    (async () => {
      unsub = await onPatternsChanged(() => {
        refresh();
      });
    })();
    return () => {
      cancelled = true;
      if (unsub) unsub();
    };
  }, []);

  // Default to the first pattern once the list comes in.
  useEffect(() => {
    if (!activePatternPath && patternNames.length > 0) {
      setActivePattern(patternNames[0]);
    }
  }, [patternNames, activePatternPath, setActivePattern]);

  const transform = panel.tiling.globalTransform;

  async function runTessellate() {
    if (!shape) return;
    setBusy('tessellate');
    setError(null);
    try {
      const resp = await tessellate({
        polygon: shape.polygon,
        group: panel.tiling.group,
        global_transform: {
          scale: transform.scale,
          rotation_deg: transform.rotationDeg,
          offset: transform.offset,
        },
        clip_bounds: {
          min_x: panel.tiling.clipBounds.minX,
          min_y: panel.tiling.clipBounds.minY,
          max_x: panel.tiling.clipBounds.maxX,
          max_y: panel.tiling.clipBounds.maxY,
        },
        lattice_scale: panel.tiling.latticeScale,
        anchor: panel.tiling.rotationAnchor,
      });
      const tiles: PlacedTile[] = resp.tiles.map((t) => ({
        id: t.tile_id,
        shapeId: shape.id,
        transform: {
          scale: transform.scale,
          rotationDeg: t.rotation_deg,
          offset: [0, 0],
        },
        polygon: t.polygon,
        centroid: t.centroid,
        areaMm2: t.area_mm2,
      }));
      // Clear mapping when tiles change — stale led→tile assignments would lie.
      const clearedMapping: Mapping = {
        tileLeds: {},
        rule: panel.mapping.rule,
        manualOverrides: {},
      };
      updatePanel(panel.id, {
        tiling: { ...panel.tiling, tiles },
        mapping: clearedMapping,
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy('idle');
    }
  }

  async function runMap() {
    if (panel.tiling.tiles.length === 0) {
      setError('No tiles yet — run Tessellate first.');
      return;
    }
    setBusy('map');
    setError(null);
    try {
      const resp = await mapLedsToTiles({
        tiles: panel.tiling.tiles.map((t) => ({ id: t.id, polygon: t.polygon })),
        led_positions: panel.ledLayout.positions.map((p) => [p[0], p[1]]),
        rule: panel.mapping.rule,
        led_radius: panel.ledLayout.pitchMm / 2,
      });
      updatePanel(panel.id, {
        mapping: {
          tileLeds: resp.mapping,
          rule: panel.mapping.rule,
          manualOverrides: {},
        },
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy('idle');
    }
  }

  const tileCount = panel.tiling.tiles.length;
  const mappedLeds = Object.values(panel.mapping.tileLeds).reduce(
    (n, idxs) => n + idxs.length,
    0,
  );

  return (
    <aside className="panel panel-right">
      <h2>Inspector</h2>

      <section className="section">
        <h3>Panel</h3>
        <Field label="LEDs">{panel.ledLayout.positions.length}</Field>
        <Field label="Pitch (mm)">{panel.ledLayout.pitchMm}</Field>
        <Field label="Color order">
          <select
            value={panel.ledLayout.colorOrder}
            onChange={(e) =>
              updatePanel(panel.id, {
                ledLayout: {
                  ...panel.ledLayout,
                  colorOrder: e.target.value as ColorOrderName,
                },
              })
            }
          >
            {COLOR_ORDERS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </Field>
      </section>

      <section className="section">
        <h3>Shape transform</h3>
        <Slider
          label="Scale"
          value={transform.scale}
          min={0.1}
          max={5}
          step={0.01}
          onChange={(v) =>
            updatePanel(panel.id, {
              tiling: {
                ...panel.tiling,
                globalTransform: { ...transform, scale: v },
              },
            })
          }
        />
        <Slider
          label="Rotation (deg)"
          value={transform.rotationDeg}
          min={-180}
          max={180}
          step={1}
          onChange={(v) =>
            updatePanel(panel.id, {
              tiling: {
                ...panel.tiling,
                globalTransform: { ...transform, rotationDeg: v },
              },
            })
          }
        />
        <Slider
          label="Offset X (mm)"
          value={transform.offset[0]}
          min={-200}
          max={200}
          step={1}
          onChange={(v) =>
            updatePanel(panel.id, {
              tiling: {
                ...panel.tiling,
                globalTransform: {
                  ...transform,
                  offset: [v, transform.offset[1]],
                },
              },
            })
          }
        />
        <Slider
          label="Offset Y (mm)"
          value={transform.offset[1]}
          min={-200}
          max={200}
          step={1}
          onChange={(v) =>
            updatePanel(panel.id, {
              tiling: {
                ...panel.tiling,
                globalTransform: {
                  ...transform,
                  offset: [transform.offset[0], v],
                },
              },
            })
          }
        />
        <Slider
          label="Lattice spacing"
          value={panel.tiling.latticeScale}
          min={0.2}
          max={3}
          step={0.01}
          onChange={(v) =>
            updatePanel(panel.id, {
              tiling: { ...panel.tiling, latticeScale: v },
            })
          }
        />
        <Slider
          label="Anchor X (motif units)"
          value={panel.tiling.rotationAnchor[0]}
          min={-400}
          max={400}
          step={1}
          onChange={(v) =>
            updatePanel(panel.id, {
              tiling: {
                ...panel.tiling,
                rotationAnchor: [v, panel.tiling.rotationAnchor[1]],
              },
            })
          }
        />
        <Slider
          label="Anchor Y (motif units)"
          value={panel.tiling.rotationAnchor[1]}
          min={-400}
          max={400}
          step={1}
          onChange={(v) =>
            updatePanel(panel.id, {
              tiling: {
                ...panel.tiling,
                rotationAnchor: [panel.tiling.rotationAnchor[0], v],
              },
            })
          }
        />
      </section>

      <section className="section">
        <h3>Tessellation</h3>
        <div className="stack">
          <button
            className="btn"
            disabled={!shape || busy !== 'idle'}
            onClick={runTessellate}
          >
            {busy === 'tessellate' ? 'Tessellating…' : 'Tessellate'}
          </button>
          <button
            className="btn"
            disabled={tileCount === 0 || busy !== 'idle'}
            onClick={runMap}
          >
            {busy === 'map' ? 'Mapping…' : 'Map LEDs to tiles'}
          </button>
          <div className="hint">
            {tileCount} tiles · {mappedLeds} / {panel.ledLayout.positions.length} LEDs
            mapped
          </div>
          {error ? <div className="hint error">{error}</div> : null}
          {!shape ? <div className="hint dim">Import an SVG shape first.</div> : null}
        </div>
      </section>

      <section className="section">
        <h3>Playback</h3>
        <Field label="Pattern">
          <select
            value={activePatternPath ?? ''}
            onChange={(e) => setActivePattern(e.target.value || null)}
          >
            {patternNames.length === 0 ? (
              <option value="">(none)</option>
            ) : null}
            {patternNames.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </Field>
        <div className="stack">
          <button
            className="btn"
            disabled={!activePatternPath}
            onClick={() => setPlaying(!playing)}
          >
            {playing ? 'Pause' : 'Play'}
          </button>
          {mappedLeds === 0 ? (
            <div className="hint dim">
              Map LEDs first to see tile-driven patterns light up.
            </div>
          ) : null}
        </div>
      </section>

      <section className="section">
        <h3>Color pipeline</h3>
        <Slider
          label="Brightness"
          value={colorConfig.brightness}
          min={0}
          max={1}
          step={0.01}
          onChange={(v) => setColorConfig({ brightness: v })}
        />
        <Slider
          label="Gamma"
          value={colorConfig.gamma}
          min={1}
          max={3}
          step={0.05}
          onChange={(v) => setColorConfig({ gamma: v })}
        />
      </section>
    </aside>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      <div className="field-value">{children}</div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="field slider">
      <label>
        <span>{label}</span>
        <span className="field-num">{formatNum(value, step)}</span>
      </label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

function formatNum(v: number, step: number): string {
  const decimals = step < 1 ? Math.max(0, -Math.floor(Math.log10(step))) : 0;
  return v.toFixed(decimals);
}
