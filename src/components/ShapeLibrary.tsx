import { useRef, useState } from 'react';
import { importSvgShape } from '../core/api';
import { useStore } from '../state/store';
import type { Shape } from '../core/structure';

export function ShapeLibrary() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<string>('');
  const shapes = useStore((s) => s.project.shapes);
  const activeShapeId = useStore((s) => s.activeShapeId);
  const addShape = useStore((s) => s.addShape);
  const setActiveShape = useStore((s) => s.setActiveShape);

  async function onFile(file: File) {
    setStatus(`reading ${file.name}…`);
    try {
      const bytes = await file.arrayBuffer();
      const res = await importSvgShape(bytes);
      const id = `shape-${Date.now()}`;
      const shape: Shape = {
        id,
        name: file.name.replace(/\.svg$/i, ''),
        svgPath: '', // we don't currently round-trip the original path text
        polygon: res.polygon,
        symmetryGroup: res.symmetry_hint,
        rotationAnchor: res.rotation_anchor,
      };
      addShape(shape);
      setStatus(
        `imported ${shape.name} — ${res.polygon.length} verts, ~${Math.round(res.width)}×${Math.round(res.height)}, ${res.symmetry_hint}`,
      );
    } catch (e) {
      setStatus(`error: ${String(e)}`);
    }
  }

  return (
    <aside className="panel panel-left">
      <h2>Shapes</h2>
      <div className="stack">
        <button
          className="btn"
          onClick={() => fileInput.current?.click()}
        >
          Import SVG…
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".svg,image/svg+xml"
          style={{ display: 'none' }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void onFile(f);
            if (fileInput.current) fileInput.current.value = '';
          }}
        />
        {status ? <p className="hint">{status}</p> : null}
        {shapes.length === 0 ? (
          <p className="placeholder">Drop an SVG here to start.</p>
        ) : (
          <ul className="shape-list">
            {shapes.map((s) => (
              <li
                key={s.id}
                className={s.id === activeShapeId ? 'active' : ''}
                onClick={() => setActiveShape(s.id)}
              >
                <span className="shape-name">{s.name}</span>
                <span className="shape-meta">{s.symmetryGroup}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
