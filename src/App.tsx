import { useEffect, useState } from 'react';
import { getSidecarBase, ping } from './core/api';
import { ShapeLibrary } from './components/ShapeLibrary';
import { Viewport } from './components/Viewport';
import { Inspector } from './components/Inspector';
import './App.css';

export default function App() {
  const [sidecarStatus, setSidecarStatus] = useState<'unknown' | 'ok' | 'down'>('unknown');
  const [sidecarBase, setSidecarBase] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const base = await getSidecarBase();
        if (cancelled) return;
        setSidecarBase(base);
        const ok = await ping();
        if (cancelled) return;
        setSidecarStatus(ok ? 'ok' : 'down');
      } catch {
        if (!cancelled) setSidecarStatus('down');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="app-root">
      <header className="app-header">
        <h1>Tessera</h1>
        <span className="subtitle">Tessellation &amp; LED mapping workbench</span>
        <span className={`sidecar-badge sidecar-${sidecarStatus}`}>
          sidecar: {sidecarStatus}
          {sidecarBase ? ` · ${sidecarBase}` : ''}
        </span>
      </header>
      <main className="three-panel">
        <ShapeLibrary />
        <section className="panel panel-center panel-viewport">
          <Viewport />
        </section>
        <Inspector />
      </main>
    </div>
  );
}
