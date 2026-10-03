import { useId } from "react";
import { PITCH } from "./geometry";

const { L, W } = PITCH;
const BOX_D = 16.5;
const BOX_W = 40.32;
const SIX_D = 5.5;
const SIX_W = 18.32;
const GOAL_W = 7.32;
const SPOT = 11;
const R = 9.15;

/** Grass + FIFA markings on a 105×68 m pitch. `pad` is the grass margin around the touchlines. */
export function PitchMarkings({ pad = 3, padX, texture = true, lineWidth = 0.24 }: {
  pad?: number; padX?: number; texture?: boolean; lineWidth?: number;
}) {
  const id = useId().replace(/:/g, "");
  const px = padX ?? pad;
  const sw = L / 16; // mowing stripes stay ~6.5 m wide and aligned to the pitch, however far the grass extends
  const first = -Math.ceil(px / sw);
  const last = Math.ceil((L + px) / sw);
  const arcDx = BOX_D - SPOT;
  const arcDy = Math.sqrt(R * R - arcDx * arcDx);
  return (
    <g>
      <defs>
        <radialGradient id={`vig-${id}`} cx="50%" cy="50%" r="75%">
          <stop offset="55%" stopColor="#000" stopOpacity={0} />
          <stop offset="100%" stopColor="#000" stopOpacity={0.45} />
        </radialGradient>
        <linearGradient id={`light-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity={0.06} />
          <stop offset="60%" stopColor="#fff" stopOpacity={0} />
        </linearGradient>
        {texture && (
          <filter id={`grain-${id}`} x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="2" seed="7" />
            <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.09 0" />
          </filter>
        )}
      </defs>
      <rect x={-px} y={-pad} width={L + 2 * px} height={W + 2 * pad} fill="var(--grass-2)" />
      {Array.from({ length: last - first }, (_, k) => first + k).map((i) =>
        ((i % 2) + 2) % 2 ? null : <rect key={i} x={i * sw} y={-pad} width={sw} height={W + 2 * pad} fill="var(--grass-1)" />,
      )}
      {texture && <rect x={-px} y={-pad} width={L + 2 * px} height={W + 2 * pad} filter={`url(#grain-${id})`} />}
      <rect x={-px} y={-pad} width={L + 2 * px} height={W + 2 * pad} fill={`url(#light-${id})`} />
      <rect x={-px} y={-pad} width={L + 2 * px} height={W + 2 * pad} fill={`url(#vig-${id})`} />

      <g fill="none" stroke="var(--pitch-line)" strokeWidth={lineWidth} strokeLinecap="round">
        <rect x={0} y={0} width={L} height={W} />
        <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
        <circle cx={L / 2} cy={W / 2} r={R} />
        {[0, 1].map((side) => {
          const x0 = side ? L : 0;
          const dir = side ? -1 : 1;
          return (
            <g key={side}>
              <rect x={side ? L - BOX_D : 0} y={(W - BOX_W) / 2} width={BOX_D} height={BOX_W} />
              <rect x={side ? L - SIX_D : 0} y={(W - SIX_W) / 2} width={SIX_D} height={SIX_W} />
              <rect x={side ? L : -1.4} y={(W - GOAL_W) / 2} width={1.4} height={GOAL_W} stroke="var(--pitch-line-soft)" />
              <path d={`M ${x0 + dir * BOX_D} ${W / 2 - arcDy} A ${R} ${R} 0 0 ${side ? 0 : 1} ${x0 + dir * BOX_D} ${W / 2 + arcDy}`} />
              {[0, W].map((y) => (
                <path key={y} d={`M ${x0} ${y === 0 ? 1 : W - 1} A 1 1 0 0 ${(side ^ (y === 0 ? 0 : 1)) ? 0 : 1} ${x0 + dir} ${y}`} />
              ))}
            </g>
          );
        })}
      </g>
      <g fill="var(--pitch-line)">
        <circle cx={L / 2} cy={W / 2} r={0.4} />
        <circle cx={SPOT} cy={W / 2} r={0.32} />
        <circle cx={L - SPOT} cy={W / 2} r={0.32} />
      </g>
    </g>
  );
}
