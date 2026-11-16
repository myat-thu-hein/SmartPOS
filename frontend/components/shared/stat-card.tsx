import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Stat tile: label, value, optional signed delta vs a named period, optional hint,
 * and an optional trend (sparkline). Values use proportional figures (no tabular-nums).
 */
export function StatCard({
  label,
  value,
  delta,
  deltaLabel,
  upIsGood = true,
  hint,
  icon,
  trend,
  className,
}: {
  label: string;
  value: ReactNode;
  delta?: number | null;
  deltaLabel?: string;
  upIsGood?: boolean;
  hint?: ReactNode;
  icon?: ReactNode;
  trend?: ReactNode;
  className?: string;
}) {
  const hasDelta = delta !== undefined && delta !== null;
  const good = hasDelta && (delta === 0 ? null : (delta > 0) === upIsGood);
  const DeltaIcon = !hasDelta || delta === 0 ? Minus : delta > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <Card className={cn("gap-3 py-4", className)}>
      <div className="flex items-center justify-between gap-3 px-5">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        {icon ? (
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground [&_svg]:size-4">
            {icon}
          </span>
        ) : null}
      </div>
      <div className="flex items-end justify-between gap-3 px-5">
        <p className="shrink-0 text-2xl font-semibold tracking-tight whitespace-nowrap sm:text-[1.75rem] sm:leading-9">{value}</p>
        {/* The trend gives way to the value: it shrinks rather than cutting the number off. */}
        {trend ? <div className="mb-1 max-w-28 min-w-10 flex-1">{trend}</div> : null}
      </div>
      {hasDelta || hint ? (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-5 text-xs text-muted-foreground">
          {hasDelta ? (
            <span
              className={cn(
                "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-medium",
                good === true && "bg-status-good/10 text-status-good-text",
                good === false && "bg-status-critical/10 text-status-critical",
                good === null && "bg-muted",
              )}
            >
              <DeltaIcon className="size-3.5" aria-hidden />
              {delta > 0 ? "+" : ""}
              {delta.toFixed(1)}%
            </span>
          ) : null}
          {hasDelta && deltaLabel ? <span>{deltaLabel}</span> : null}
          {hint ? <span>{hint}</span> : null}
        </div>
      ) : null}
    </Card>
  );
}
