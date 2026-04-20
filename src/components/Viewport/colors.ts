import { Color } from 'three';

// Stable hash → hue per tile id. HSL so the saturation/lightness stay
// consistent; the only thing that varies is the hue.
export function tileColor(id: string): Color {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) >>> 0;
  }
  const hue = (h % 360) / 360;
  return new Color().setHSL(hue, 0.55, 0.55);
}
