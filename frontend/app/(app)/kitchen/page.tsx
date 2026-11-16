"use client";

import { ChefHat, Clock, Loader2, RefreshCw, StickyNote } from "lucide-react";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { QueryState } from "@/components/shared/query-state";
import { KitchenStatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatTime, minutesSince } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useLiveEvents, useLiveRefetchInterval } from "@/lib/realtime";
import { cn } from "@/lib/utils";
import type { KitchenStatus, KitchenTicket } from "@/types/api";

const COLUMNS: { status: KitchenStatus; title: string }[] = [
  { status: "NEW", title: "New" },
  { status: "PREPARING", title: "Preparing" },
  { status: "READY", title: "Ready" },
];

const NEXT: Partial<
  Record<KitchenStatus, { to: KitchenStatus; label: string }>
> = {
  NEW: { to: "PREPARING", label: "Start preparing" },
  PREPARING: { to: "READY", label: "Mark ready" },
  READY: { to: "COMPLETED", label: "Mark completed" },
};

/** Minutes since the ticket entered the kitchen; the clock ticks every 30 s. */
function useNow(intervalMs = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

export default function KitchenPage() {
  const { t } = useI18n();
  const [showCompleted, setShowCompleted] = useState(false);
  const statuses: KitchenStatus[] = showCompleted
    ? ["NEW", "PREPARING", "READY", "COMPLETED"]
    : ["NEW", "PREPARING", "READY"];
  const refetchInterval = useLiveRefetchInterval(5_000);
  const query = useApi<KitchenTicket[]>(
    ["kitchen"],
    "/kitchen/orders",
    { status: statuses },
    { refetchInterval },
  );
  const now = useNow();
  // Tickets that arrive while the screen is open flash once so the cooks notice them.
  const [fresh, setFresh] = useState<Set<string>>(() => new Set());
  useLiveEvents((event) => {
    if (event.type !== "order.confirmed" || !event.entity_id) return;
    const id = event.entity_id;
    setFresh((current) => new Set(current).add(id));
    setTimeout(
      () =>
        setFresh((current) => {
          const next = new Set(current);
          next.delete(id);
          return next;
        }),
      4000,
    );
  });

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <ChefHat className="size-6" aria-hidden /> {t("Kitchen Display")}
          </h1>
          <p className="text-sm text-muted-foreground">
            New orders appear instantly. Oldest tickets first.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Label className="font-normal">
            <Switch
              checked={showCompleted}
              onCheckedChange={setShowCompleted}
            />{" "}
            Show completed (12 h)
          </Label>
          <Button
            variant="outline"
            size="sm"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
          >
            <RefreshCw
              className={query.isFetching ? "animate-spin" : undefined}
            />{" "}
            Refresh
          </Button>
        </div>
      </div>
      <QueryState query={query}>
        {(tickets) => (
          <div
            className={cn(
              "grid gap-4",
              showCompleted ? "lg:grid-cols-4" : "lg:grid-cols-3",
            )}
          >
            {[
              ...COLUMNS,
              ...(showCompleted
                ? [{ status: "COMPLETED" as KitchenStatus, title: "Completed" }]
                : []),
            ].map((column) => {
              const items = tickets.filter(
                (ticket) => ticket.kitchen_status === column.status,
              );
              return (
                <section
                  key={column.status}
                  aria-label={column.title}
                  className="flex flex-col gap-3 rounded-xl bg-muted/50 p-3"
                >
                  <h2 className="flex items-center justify-between px-1 text-lg font-semibold">
                    {t(column.title)}
                    <span className="rounded-full bg-card px-2.5 text-base tabular">
                      {items.length}
                    </span>
                  </h2>
                  {items.length ? (
                    items.map((ticket) => (
                      <Ticket
                        key={ticket.order_id}
                        ticket={ticket}
                        now={now}
                        fresh={fresh.has(ticket.order_id)}
                      />
                    ))
                  ) : (
                    <EmptyState
                      title="No tickets"
                      className="border-0 bg-transparent py-8"
                    />
                  )}
                </section>
              );
            })}
          </div>
        )}
      </QueryState>
    </div>
  );
}

function Ticket({
  ticket,
  now,
  fresh = false,
}: {
  ticket: KitchenTicket;
  now: number;
  fresh?: boolean;
}) {
  const { t } = useI18n();
  const { can } = useAuth();
  const next = NEXT[ticket.kitchen_status];
  const started = ticket.confirmed_at ?? ticket.created_at;
  const minutes = minutesSince(started, now);
  const late =
    ticket.kitchen_status !== "COMPLETED" && ticket.kitchen_status !== "READY";
  const update = useApiMutation(
    (status: KitchenStatus) =>
      api<KitchenTicket>(`/kitchen/orders/${ticket.order_id}/status`, {
        method: "POST",
        body: { status },
      }),
    { invalidate: ["kitchen", "orders", "order", "dashboard", "tables"] },
  );
  const allowed =
    next &&
    (can("kitchen:update") ||
      (next.to === "COMPLETED" && can("orders:complete")));
  return (
    <article
      className={cn(
        "flex flex-col gap-3 rounded-xl border-2 bg-card p-4 shadow-card",
        late && minutes >= 25
          ? "border-status-critical"
          : late && minutes >= 15
            ? "border-status-serious"
            : "border-transparent",
        fresh && "animate-flash border-primary",
      )}
    >
      {fresh ? <span className="sr-only">New order</span> : null}
      <header className="flex items-start justify-between gap-2">
        <div>
          <p className="text-2xl font-bold tracking-tight">
            #{ticket.display_number}
          </p>
          <p className="text-base font-medium">
            {ticket.order_type === "DINE_IN" ? ticket.label : t("Takeaway")}
          </p>
        </div>
        <div className="text-right">
          <KitchenStatusBadge status={ticket.kitchen_status} />
          <p
            className={cn(
              "mt-1 flex items-center justify-end gap-1 text-sm font-semibold tabular",
              late && minutes >= 25
                ? "text-status-critical"
                : "text-muted-foreground",
            )}
          >
            <Clock className="size-4" aria-hidden /> {minutes} min
          </p>
          <p className="text-xs text-muted-foreground">
            in at {formatTime(started)}
          </p>
        </div>
      </header>
      <ul className="grid gap-2">
        {ticket.items.map((item) => (
          <li key={item.id} className="text-lg leading-snug">
            <span className="mr-2 inline-flex min-w-8 justify-center rounded-md bg-secondary px-1.5 font-bold tabular">
              {item.quantity}×
            </span>
            <span className="font-medium">{item.product_name}</span>
            {item.modifiers.length ? (
              <p className="ml-10 text-sm text-muted-foreground">
                {item.modifiers.join(" · ")}
              </p>
            ) : null}
            {item.notes ? (
              <p className="ml-10 flex items-center gap-1 text-sm font-medium text-status-critical">
                <StickyNote className="size-3.5" aria-hidden /> {item.notes}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
      {ticket.notes ? (
        <p className="rounded-md border border-status-warning/60 bg-status-warning/10 px-3 py-2 text-sm font-medium">
          Note: {ticket.notes}
        </p>
      ) : null}
      {next && allowed ? (
        <Button
          size="xl"
          className="w-full"
          onClick={() => update.mutate(next.to)}
          disabled={update.isPending}
        >
          {update.isPending ? <Loader2 className="animate-spin" /> : null}
          {t(next.label)}
        </Button>
      ) : null}
    </article>
  );
}
