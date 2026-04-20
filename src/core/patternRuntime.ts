// Pattern loader + hot-reload wiring.
//
// Flow:
//   1. Rust side `list_patterns` enumerates {project_root}/patterns/*.js|.mjs.
//   2. Rust side `read_pattern` returns the file text.
//   3. We wrap the text in a Blob, create an object URL, and dynamic-import
//      that URL. Each reload gets a fresh URL so module caching never bites.
//   4. Rust side `watch_patterns_dir` emits `patterns-changed` events via
//      notify::RecommendedWatcher. We debounce and re-run `list_patterns` +
//      reload the active pattern.
//
// The render loop itself (60 Hz RAF) lives inside the Viewport component so
// it can drive the InstancedMesh directly via useFrame — this module is
// stateless bootstrapping and file I/O.

import { invoke } from '@tauri-apps/api/core';
import { listen, UnlistenFn } from '@tauri-apps/api/event';
import { isPatternModule, PatternModule } from './patternApi';

export type LoadResult =
  | { ok: true; module: PatternModule; source: string }
  | { ok: false; error: string };

export async function listPatterns(): Promise<string[]> {
  try {
    return await invoke<string[]>('list_patterns');
  } catch (e) {
    console.error('list_patterns failed', e);
    return [];
  }
}

export async function readPatternSource(name: string): Promise<string> {
  return await invoke<string>('read_pattern', { name });
}

export async function writePatternSource(name: string, content: string): Promise<string> {
  return await invoke<string>('write_pattern', { name, content });
}

export async function loadPattern(name: string): Promise<LoadResult> {
  let source: string;
  try {
    source = await readPatternSource(name);
  } catch (e) {
    return { ok: false, error: `read ${name}: ${String(e)}` };
  }

  const blob = new Blob([source], { type: 'application/javascript' });
  const url = URL.createObjectURL(blob);
  try {
    const mod = await import(/* @vite-ignore */ url);
    if (!isPatternModule(mod)) {
      return {
        ok: false,
        error: `${name}: module does not export a render() function`,
      };
    }
    return { ok: true, module: mod, source };
  } catch (e) {
    return { ok: false, error: `${name}: ${String(e)}` };
  } finally {
    // The module is fully resolved and held by the JS engine; revoking the
    // URL now is safe and frees the Blob.
    URL.revokeObjectURL(url);
  }
}

export async function startWatching(patternsDir: string): Promise<void> {
  await invoke('watch_patterns_dir', { path: patternsDir });
}

export async function onPatternsChanged(
  handler: (paths: string[]) => void,
): Promise<UnlistenFn> {
  return await listen<{ kind: string; paths: string[] }>(
    'patterns-changed',
    (ev) => {
      handler(ev.payload.paths ?? []);
    },
  );
}

export async function getProjectRoot(): Promise<string> {
  return await invoke<string>('project_root');
}

// Join a project root with /patterns. Works for both Windows backslash and
// posix paths that Tauri might hand back.
export function patternsDirFor(projectRoot: string): string {
  const sep = projectRoot.includes('\\') ? '\\' : '/';
  return projectRoot.endsWith(sep) ? `${projectRoot}patterns` : `${projectRoot}${sep}patterns`;
}
