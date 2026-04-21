// Global app state (zustand).
//
// Hot-path data (per-frame LED buffers, current audio/motion frame, etc.) is
// NOT kept in zustand — it lives in module-level mutable singletons so the
// 60 Hz render loop never triggers React re-renders. Zustand is only for
// things the UI cares about: the current project, loaded shapes, active
// pattern, and persistent config.

import { create } from 'zustand';
import {
  default32x32Grid,
  emptyMapping,
  type Panel,
  type Project,
  type Shape,
} from '../core/structure';
import { defaultColorConfig, type ColorConfig } from '../core/colorSpace';

function defaultPanel(): Panel {
  return {
    id: 'panel-0',
    tiling: {
      shapeId: '',
      group: 'p3',
      globalTransform: { scale: 1, rotationDeg: 0, offset: [0, 0] },
      latticeScale: 1,
      rotationAnchor: [0, 0],
      clipBounds: { minX: -160, minY: -160, maxX: 160, maxY: 160 },
      tiles: [],
    },
    ledLayout: default32x32Grid(10),
    mapping: emptyMapping(),
  };
}

function defaultProject(): Project {
  return {
    name: 'Untitled',
    formatVersion: 1,
    shapes: [],
    panels: [defaultPanel()],
    activePatternPath: null,
  };
}

export type UiState = {
  project: Project;
  activePanelId: string;
  activeShapeId: string | null;
  colorConfig: ColorConfig;
  playing: boolean;

  addShape: (shape: Shape) => void;
  setActiveShape: (id: string | null) => void;
  updatePanel: (id: string, patch: Partial<Panel>) => void;
  setColorConfig: (patch: Partial<ColorConfig>) => void;
  setActivePattern: (path: string | null) => void;
  setPlaying: (p: boolean) => void;
};

export const useStore = create<UiState>((set) => ({
  project: defaultProject(),
  activePanelId: 'panel-0',
  activeShapeId: null,
  colorConfig: defaultColorConfig,
  playing: false,

  addShape: (shape) =>
    set((s) => ({
      project: {
        ...s.project,
        shapes: [...s.project.shapes, shape],
        panels: seedAnchorFromShape(s.project.panels, s.activePanelId, shape),
      },
      activeShapeId: shape.id,
    })),

  setActiveShape: (id) =>
    set((s) => {
      const shape = id ? s.project.shapes.find((sh) => sh.id === id) ?? null : null;
      return {
        activeShapeId: id,
        project: shape
          ? {
              ...s.project,
              panels: seedAnchorFromShape(s.project.panels, s.activePanelId, shape),
            }
          : s.project,
      };
    }),

  updatePanel: (id, patch) =>
    set((s) => ({
      project: {
        ...s.project,
        panels: s.project.panels.map((p) =>
          p.id === id ? { ...p, ...patch } : p
        ),
      },
    })),

  setColorConfig: (patch) =>
    set((s) => ({ colorConfig: { ...s.colorConfig, ...patch } })),

  setActivePattern: (path) =>
    set((s) => ({ project: { ...s.project, activePatternPath: path } })),

  setPlaying: (p) => set({ playing: p }),
}));

export function selectActivePanel(s: UiState): Panel {
  return s.project.panels.find((p) => p.id === s.activePanelId) ?? s.project.panels[0];
}

export function selectActiveShape(s: UiState): Shape | null {
  if (!s.activeShapeId) return null;
  return s.project.shapes.find((sh) => sh.id === s.activeShapeId) ?? null;
}

function seedAnchorFromShape(panels: Panel[], activePanelId: string, shape: Shape): Panel[] {
  return panels.map((p) =>
    p.id === activePanelId
      ? {
          ...p,
          tiling: {
            ...p.tiling,
            shapeId: shape.id,
            rotationAnchor: shape.rotationAnchor,
          },
        }
      : p,
  );
}
