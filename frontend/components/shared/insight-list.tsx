import { AlertTriangle, ArrowRight, ChefHat, Info, OctagonAlert, TrendingUp } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";
import type { Insight, InsightSeverity } from "@/types/api";

const STYLE: Record<InsightSeverity, { icon: typeof Info; tone: string; label: string }> = {
  critical: { icon: OctagonAlert, tone: "bg-status-critical/12 text-status-critical", label: "Urgent" },
  warning: { icon: AlertTriangle, tone: "bg-status-warning/18 text-foreground", label: "Attention" },
  positive: { icon: TrendingUp, tone: "bg-status-good/12 text-status-good-text", label: "Good news" },
  info: { icon: Info, tone: "bg-series-1/10 text-series-1", label: "Info" },
};

/** Explainable insights with the evidence in plain words and a link to act on each. */
export function InsightList({ insights, limit, className }: { insights: Insight[]; limit?: number; className?: string }) {
  const shown = limit ? insights.slice(0, limit) : insights;
  return (
    <ul className={cn("grid gap-1", className)}>
      {shown.map((insight) => {
        const { icon: Icon, tone, label } = STYLE[insight.severity] ?? STYLE.info;
        const KindIcon = insight.category === "kitchen" && insight.severity === "info" ? ChefHat : Icon;
        const body = (
          <>
            <span className={cn("mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full", tone)}>
              <KindIcon className="size-3.5" aria-hidden />
              <span className="sr-only">{label}: </span>
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm leading-snug font-medium">{insight.title}</span>
              <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">{insight.detail}</span>
            </span>
            {insight.link ? (
              <span className="mt-0.5 flex shrink-0 items-center gap-1 text-xs font-medium text-primary">
                <span className={cn(!insight.action && "sr-only")}>{insight.action ?? "Open"}</span>
                <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </span>
            ) : null}
          </>
        );
        return (
          <li key={insight.key}>
            {insight.link ? (
              <Link
                href={insight.link}
                className="group flex items-start gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-accent/60 focus-visible:bg-accent/60"
              >
                {body}
              </Link>
            ) : (
              <div className="flex items-start gap-3 px-2 py-2.5">{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
