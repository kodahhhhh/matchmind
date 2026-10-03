export const PITCH = { L: 105, W: 68 };

/** SPADL y (origin bottom-left, up) → SVG y (down). */
export const sy = (y: number) => PITCH.W - y;
