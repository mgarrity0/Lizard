// WS2812 gamma + color-order + brightness.
//
// The point of this module is sim/hardware parity: the values we send to the
// renderer (and that the exporters will bake or emit) must be the same values
// the physical LEDs will see, so the side-by-side test (viewport vs. phone
// photo of the lit panel) lines up.
//
// Pipeline (pattern output -> on-screen pixel):
//   1. Pattern writes linear 8-bit RGB into the frame buffer (`out[i*3+0..2]`).
//   2. applyBrightness() scales by the brightness slider (duty cycle).
//   3. applyGamma() maps each channel through pow(v/255, gamma).
//   4. applyColorOrder() reorders channels for the strip's wiring (GRB by
//      default on WS2812).
//   5. Result is uploaded to InstancedMesh instance-color buffer as floats
//      in [0,1] (Three.js wants linear floats; we set its output encoding to
//      sRGB so display math is correct).

export type ColorOrder = 'RGB' | 'RBG' | 'GRB' | 'GBR' | 'BRG' | 'BGR';

export type ColorTrim = {
  // Per-channel trim multipliers, applied BEFORE gamma. 1.0 = no trim.
  r: number;
  g: number;
  b: number;
};

export type ColorConfig = {
  // Gamma for each channel. 2.2 is the classic sRGB value; 2.6 is what most
  // FastLED users land on for WS281x chips because the PWM duty is perceptual.
  gamma: number;
  // Duty-cycle brightness (0..1). Applied linearly to the 8-bit value
  // before gamma, matching how WLED / FastLED scale master brightness.
  brightness: number;
  colorOrder: ColorOrder;
  trim: ColorTrim;
};

export const defaultColorConfig: ColorConfig = {
  gamma: 2.6,
  brightness: 0.6,
  // Default to RGB in the simulator so patterns look "as authored". The
  // physical WS2812 strip is wired GRB; the exporter will emit bytes in
  // that order. Setting colorOrder='GRB' here is useful to visualize what
  // happens when your firmware's byte-order config is wrong.
  colorOrder: 'RGB',
  trim: { r: 1.0, g: 1.0, b: 1.0 },
};

// ---------- single-pixel helpers ----------

export function applyBrightness(v: number, brightness: number): number {
  // v in 0..255, returns 0..255
  return Math.max(0, Math.min(255, v * brightness));
}

export function applyGamma(v: number, gamma: number): number {
  // v in 0..255, returns linear float in [0,1] suitable for a Three.js
  // instance-color buffer (Canvas `outputColorSpace` = sRGB will do the
  // sRGB encoding step for us).
  const n = Math.max(0, Math.min(1, v / 255));
  return Math.pow(n, gamma);
}

// Reorder RGB input triplet per the strip's wiring. The output triplet is
// what gets sent down the wire; for the simulator we keep the visual in RGB
// but still apply the reorder so that e.g. swapping color-order in config
// visibly reproduces the hardware bug.
export function applyColorOrder(
  r: number,
  g: number,
  b: number,
  order: ColorOrder,
): [number, number, number] {
  switch (order) {
    case 'RGB': return [r, g, b];
    case 'RBG': return [r, b, g];
    case 'GRB': return [g, r, b];
    case 'GBR': return [g, b, r];
    case 'BRG': return [b, r, g];
    case 'BGR': return [b, g, r];
  }
}

// ---------- frame-wide helper ----------

/**
 * Take a pattern's linear 8-bit output buffer and produce a Float32 linear
 * buffer ready for Three.js InstancedMesh.instanceColor.
 *
 * rgbOut length = ledCount * 3. linearOut length = ledCount * 3 (in place).
 */
export function bakeFrameToLinearFloats(
  rgbOut: Uint8ClampedArray,
  linearOut: Float32Array,
  cfg: ColorConfig,
): void {
  const { gamma, brightness, colorOrder, trim } = cfg;
  const n = rgbOut.length;
  for (let i = 0; i < n; i += 3) {
    const rIn = rgbOut[i + 0] * trim.r;
    const gIn = rgbOut[i + 1] * trim.g;
    const bIn = rgbOut[i + 2] * trim.b;
    const [rB, gB, bB] = applyColorOrder(rIn, gIn, bIn, colorOrder);
    const rBr = applyBrightness(rB, brightness);
    const gBr = applyBrightness(gB, brightness);
    const bBr = applyBrightness(bB, brightness);
    linearOut[i + 0] = applyGamma(rBr, gamma);
    linearOut[i + 1] = applyGamma(gBr, gamma);
    linearOut[i + 2] = applyGamma(bBr, gamma);
  }
}

// Produce a 256-entry gamma LUT for exporters (e.g. the FastLED sketch uses
// this table at runtime on the ESP32). Returns 0..255 byte values — the
// round-trip a real strip will see after the controller applies the same
// curve.
export function gammaLut(gamma: number): Uint8Array {
  const lut = new Uint8Array(256);
  for (let i = 0; i < 256; i++) {
    lut[i] = Math.round(Math.pow(i / 255, gamma) * 255);
  }
  return lut;
}
