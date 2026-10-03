// FIFA-standard markings on a 105×68 m pitch (SPADL frame, origin bottom-left → SVG y is flipped by the parent).
const L = 105;
const W = 68;
const BOX_D = 16.5;
const BOX_W = 40.32;
const SIX_D = 5.5;
const SIX_W = 18.32;
const GOAL_W = 7.32;
const SPOT = 11;
const R = 9.15;

export function PitchMarkings({ stripes = 14 }: { stripes?: number }) {
  const sw = L / stripes;
  // penalty arc: the part of the r=9.15 circle around the spot that lies outside the box
  const arcDx = BOX_D - SPOT;
  const arcDy = Math.sqrt(R * R - arcDx * arcDx);
  return (
    <g>
      <defs>
        <radialGradient id="pitch-glow" cx="50%" cy="45%" r="70%">
          <stop offset="0%" stopColor="var(--pitch-glow)" />
          <stop offset="100%" stopColor="transparent" />
        </radialGradient>
      </defs>
      <rect x={-3} y={-3} width={L + 6} height={W + 6} rx={1.6} fill="var(--pitch)" />
      {Array.from({ length: stripes }, (_, i) =>
        i % 2 ? <rect key={i} x={i * sw} y={0} width={sw} height={W} fill="var(--pitch-stripe)" /> : null,
      )}
      <rect x={-3} y={-3} width={L + 6} height={W + 6} fill="url(#pitch-glow)" />
      <g fill="none" stroke="var(--pitch-line)" strokeWidth={0.22} strokeLinecap="round">
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
              <rect x={side ? L : -1.6} y={(W - GOAL_W) / 2} width={1.6} height={GOAL_W} strokeWidth={0.18} />
              <path d={`M ${x0 + dir * BOX_D} ${W / 2 - arcDy} A ${R} ${R} 0 0 ${side ? 0 : 1} ${x0 + dir * BOX_D} ${W / 2 + arcDy}`} />
              {[0, W].map((y) => (
                <path key={y} d={`M ${x0} ${y === 0 ? 1 : W - 1} A 1 1 0 0 ${(side ^ (y === 0 ? 0 : 1)) ? 0 : 1} ${x0 + dir} ${y}`} />
              ))}
            </g>
          );
        })}
      </g>
      <g fill="var(--pitch-line)">
        <circle cx={L / 2} cy={W / 2} r={0.35} />
        <circle cx={SPOT} cy={W / 2} r={0.3} />
        <circle cx={L - SPOT} cy={W / 2} r={0.3} />
      </g>
    </g>
  );
}

export const PITCH = { L, W };
