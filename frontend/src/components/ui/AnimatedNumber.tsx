import { useEffect, useRef, useState } from "react";

/** Eases from the previous value to the new one (count-up on mount). */
export function useTween(value: number, ms = 650, from?: number) {
  const [v, setV] = useState(from ?? value);
  const prev = useRef(from ?? value);
  useEffect(() => {
    const start = prev.current;
    const delta = value - start;
    if (Math.abs(delta) < 1e-9) return;
    const t0 = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      const cur = start + delta * e;
      prev.current = cur;
      setV(cur);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return v;
}

export function AnimatedNumber({ value, format = (v) => String(Math.round(v)), ms, from }: {
  value: number; format?: (v: number) => string; ms?: number; from?: number;
}) {
  const v = useTween(value, ms, from);
  return <>{format(v)}</>;
}
