import type { ReactNode, RefObject } from "react";
import { Link, NavLink, useNavigate } from "react-router";
import { motion, useScroll, useTransform } from "motion/react";
import { List } from "@phosphor-icons/react";
import { Logo } from "./Logo";
import { SearchButton } from "../search/SearchPalette";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "./dropdown-menu";

export const NAV: [string, string][] = [["/", "Matches"], ["/players", "Underrated players"], ["/backtest", "Versus the bookies"]];

/** Site header for the full-page screens: logo, primary nav with the current page marked, search.
 *  Sticky inside the page's scroll container; its backdrop fades in once the page scrolls.
 *  Below md the nav folds into a menu so every page stays one tap away. */
export function SiteHeader({ scroller }: { scroller: RefObject<HTMLDivElement | null> }) {
  const { scrollY } = useScroll({ container: scroller });
  const backdrop = useTransform(scrollY, [0, 48], [0, 1]);
  return (
    <header className="sticky top-0 z-20">
      <motion.div aria-hidden className="absolute inset-0 border-b border-line bg-bg/85 backdrop-blur-xl" style={{ opacity: backdrop }} />
      <div className="relative mx-auto flex h-16 max-w-[1280px] items-center justify-between gap-3 px-4 sm:px-5 md:h-[72px] md:px-8">
        <Link to="/" aria-label="MatchPulse home" className="rounded-xl"><Logo size={30} /></Link>
        <nav aria-label="Primary" className="flex items-center gap-1 md:gap-1.5">
          {NAV.map(([to, label]) => <Item key={to} to={to} end={to === "/"}>{label}</Item>)}
          <SearchButton className="ml-2 hidden rounded-full sm:flex" />
          <SearchButton compact className="h-10 rounded-full sm:hidden" />
          <MobileMenu />
        </nav>
      </div>
    </header>
  );
}

function Item({ to, end, children }: { to: string; end?: boolean; children: ReactNode }) {
  return (
    <NavLink to={to} end={end}
      className={({ isActive }) => `hidden rounded-full px-3 py-2 text-[14px] font-medium transition-colors duration-150 md:block ${isActive ? "bg-surface-2 text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}>
      {children}
    </NavLink>
  );
}

/** Phone menu: the same pages as the desktop nav. */
export function MobileMenu({ className = "md:hidden" }: { className?: string }) {
  const navigate = useNavigate();
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger aria-label="Menu"
        className={`grid size-10 place-items-center rounded-full bg-surface-2 text-ink-2 ring-1 ring-line transition-[background-color,color,transform] duration-150 ease-out hover:bg-surface-3 hover:text-ink active:scale-[0.97] data-[state=open]:bg-surface-3 data-[state=open]:text-ink ${className}`}>
        <List size={18} weight="bold" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={8} className="min-w-[220px] rounded-2xl border-0 bg-surface-2 p-1.5 text-ink shadow-[0_24px_60px_-12px_rgba(0,0,0,0.8)] ring-1 ring-line-strong">
        {NAV.map(([to, label]) => (
          <DropdownMenuItem key={to} onSelect={() => navigate(to)}
            className="rounded-xl px-3 py-2.5 text-[15px] font-medium text-ink-2 focus:bg-surface-3 focus:text-ink">
            {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
