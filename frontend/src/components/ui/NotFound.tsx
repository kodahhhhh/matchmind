import { useRef } from "react";
import { Link } from "react-router";
import { Line, Stagger } from "./motion";
import { SiteHeader } from "./SiteHeader";

/** Unknown route: say so plainly and point back to the matches. */
export function NotFound() {
  const scroller = useRef<HTMLDivElement>(null);
  return (
    <div ref={scroller} className="scroll-thin h-full overflow-y-auto">
      <SiteHeader scroller={scroller} />
      <main className="mx-auto max-w-[1280px] px-5 pb-28 pt-20 md:px-8 md:pt-28">
        <Stagger onMount>
          <Line n={1} as="p" className="numeral text-[72px] leading-none text-ink-4">404</Line>
          <Line n={2} as="h1" className="mt-6 text-[38px] font-semibold leading-[1.06] tracking-[-0.04em] text-ink md:text-[48px]">This page isn't on the pitch</Line>
          <Line n={3} as="p" className="mt-5 max-w-[46ch] text-[17px] leading-[1.6] text-ink-2">The link may be out of date. Every match is still one click away.</Line>
          <Line n={4} as="div" className="mt-9">
            <Link to="/" className="inline-flex rounded-full bg-ink px-5 py-2.5 text-[14.5px] font-semibold text-bg transition-[transform,background-color] duration-150 ease-out hover:bg-ink-2 active:scale-[0.97]">
              Browse matches
            </Link>
          </Line>
        </Stagger>
      </main>
    </div>
  );
}
