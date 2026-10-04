import type { ReactNode } from "react";
import { Info } from "@phosphor-icons/react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { GLOSSARY, type GlossaryKey } from "../../lib/glossary";

/** A label with a small info button that explains the stat in plain words (hover, tap or focus). */
export function Explain({ term, children, className = "" }: { term: GlossaryKey; children: ReactNode; className?: string }) {
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" className={`pointer-events-auto inline-flex items-center gap-1 rounded-sm text-left underline decoration-dotted decoration-1 underline-offset-[3px] focus-visible:outline-2 focus-visible:outline-[var(--ai)] ${className}`}>
            {children}
            <Info size={11} weight="bold" className="shrink-0 opacity-70" aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[240px] bg-surface-4 text-[12px] leading-[1.45] text-ink ring-1 ring-line [&>svg]:bg-surface-4 [&>svg]:fill-surface-4">
          {GLOSSARY[term]}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
