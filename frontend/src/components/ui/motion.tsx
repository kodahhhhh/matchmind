// React bindings for the transitions.dev snippets in theme/transitions.css.
import { useEffect, useId, useRef, useState, type ElementType, type PointerEvent, type ReactNode } from "react";
import { useInView, useReducedMotion } from "motion/react";

/** Texts reveal: lines rise in with a blurred stagger once the block scrolls into view (or on mount). */
export function Stagger({ children, className = "", onMount = false, as: Tag = "div" }: {
  children: ReactNode; className?: string; onMount?: boolean; as?: ElementType;
}) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    if (!onMount) return;
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, [onMount]);
  const shown = onMount ? mounted : inView;
  return <Tag ref={ref} className={`t-stagger ${shown ? "is-shown" : ""} ${className}`}>{children}</Tag>;
}

/** One line of a <Stagger>; `n` sets its place in the cascade (1-based). */
export function Line({ n, children, className = "", as: Tag = "span" }: { n: number; children: ReactNode; className?: string; as?: ElementType }) {
  return <Tag className={`t-stagger-line t-stagger-line--${n} ${className}`}>{children}</Tag>;
}

const SPINS = 2;

/** Spinning counter: each digit is a 0-9 reel that spins and lands when `active` turns true. */
export function SpinningNumber({ value, active, delay = 0 }: { value: number; active: boolean; delay?: number }) {
  const reduce = useReducedMotion();
  const chars = value.toLocaleString("en-GB").split("");
  let col = 0;
  return (
    <>
      <span className="sr-only">{value.toLocaleString("en-GB")}</span>
      {reduce ? <span aria-hidden>{value.toLocaleString("en-GB")}</span> : (
        <span className="t-reel" aria-hidden>
          {chars.map((c, i) => (/\d/.test(c)
            ? <ReelCol key={i} digit={Number(c)} col={col++} active={active} delay={delay} />
            : <span key={i}>{c}</span>))}
        </span>
      )}
    </>
  );
}

function ReelCol({ digit, col, active, delay }: { digit: number; col: number; active: boolean; delay: number }) {
  const strip = useRef<HTMLSpanElement>(null);
  const blur = useRef<SVGFEGaussianBlurElement>(null);
  const id = `reel-blur-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  useEffect(() => {
    if (!active || !strip.current) return;
    const el = strip.current;
    const cs = getComputedStyle(document.documentElement);
    const dur = parseFloat(cs.getPropertyValue("--reel-dur")) || 1400;
    const stagger = parseFloat(cs.getPropertyValue("--reel-stagger")) || 90;
    const maxBlur = parseFloat(cs.getPropertyValue("--reel-spin-blur")) || 3;
    const start = delay + col * stagger;
    el.style.transition = `transform var(--reel-dur) var(--reel-ease) ${start}ms`;
    el.style.transform = `translateY(calc(var(--reel-cell) * -${SPINS * 10 + digit}))`;
    // vertical-only motion blur that decays as the reel settles
    let raf = 0;
    const t0 = performance.now() + start;
    const tick = (t: number) => {
      const k = Math.min(1, Math.max(0, (t - t0) / (dur * 0.7)));
      blur.current?.setAttribute("stdDeviation", `0 ${(maxBlur * (1 - k) * (t >= t0 ? 1 : 0)).toFixed(2)}`);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, digit, col, delay]);

  return (
    <span className="t-reel-col">
      <svg width="0" height="0" className="absolute"><filter id={id}><feGaussianBlur ref={blur} stdDeviation="0 0" /></filter></svg>
      <span ref={strip} className="t-reel-strip" style={{ filter: `url(#${id})` }}>
        {Array.from({ length: (SPINS + 1) * 10 }, (_, i) => <span key={i} className="t-reel-digit">{i % 10}</span>)}
      </span>
    </span>
  );
}

/** Card tilt: tracks the pointer on the flat wrapper and writes rotation + glare position onto the card. */
export function Tilt({ children, className = "", cardClassName = "", max = 10 }: {
  children: ReactNode; className?: string; cardClassName?: string; max?: number;
}) {
  const wrap = useRef<HTMLSpanElement>(null);
  const card = useRef<HTMLSpanElement>(null);
  const reduce = useReducedMotion();

  const reset = () => {
    wrap.current?.classList.remove("is-hover");
    card.current?.classList.remove("is-tilting");
    card.current?.style.setProperty("--tilt-rx", "0deg");
    card.current?.style.setProperty("--tilt-ry", "0deg");
  };
  const track = (e: PointerEvent) => {
    if (reduce || e.pointerType !== "mouse" || !wrap.current || !card.current) return;
    const r = wrap.current.getBoundingClientRect();
    const px = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    const py = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
    wrap.current.classList.add("is-hover");
    card.current.classList.add("is-tilting");
    card.current.style.setProperty("--tilt-ry", `${((px - 0.5) * max).toFixed(2)}deg`);
    card.current.style.setProperty("--tilt-rx", `${((0.5 - py) * max).toFixed(2)}deg`);
    card.current.style.setProperty("--tilt-gx", `${(px * 100).toFixed(1)}%`);
    card.current.style.setProperty("--tilt-gy", `${(py * 100).toFixed(1)}%`);
  };

  return (
    <span ref={wrap} className={`t-tilt block ${className}`} onPointerMove={track} onPointerLeave={reset}>
      <span ref={card} className={`t-tilt-card block ${cardClassName}`}>
        {children}
        <span className="t-tilt-glare" aria-hidden />
      </span>
    </span>
  );
}

/** Learn-more chevron: shifts right and opens into an arrow while its `.t-learn` parent is hovered. */
export function LearnChevron() {
  return (
    <span className="t-learn-chevron" aria-hidden>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
        <path className="t-learn-arm t-learn-arm-top" d="M6 4L10 8" />
        <path className="t-learn-arm t-learn-arm-bot" d="M10 8L6 12" />
      </svg>
    </span>
  );
}

/** Skeleton reveal for photos: a pulsing placeholder cross-blurs into the image once it has loaded. */
export function RevealImage({ src, alt, className = "", fallback }: { src: string | null; alt: string; className?: string; fallback: ReactNode }) {
  // key this component by src: state is per image
  const [state, setState] = useState<"loading" | "loaded" | "error">("loading");
  const failed = !src || state === "error";
  return (
    <span className={`t-skel block ${state !== "loading" || failed ? "is-revealed" : ""} ${className}`}>
      <span className={`t-skel-skeleton block ${state === "loading" && !failed ? "is-pulsing" : ""}`} aria-hidden><span className="block h-full w-full bg-surface-3" /></span>
      <span className="t-skel-content block">
        {failed ? fallback : (
          <img src={src} alt={alt} loading="lazy" decoding="async" draggable={false}
            onLoad={() => setState("loaded")} onError={() => setState("error")}
            className="h-full w-full object-cover object-[50%_20%]" />
        )}
      </span>
    </span>
  );
}
