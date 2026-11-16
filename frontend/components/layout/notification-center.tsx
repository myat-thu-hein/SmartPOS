"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell, CheckCheck, Info, OctagonAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useApi } from "@/hooks/use-api";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatRelativeTime } from "@/lib/format";
import { useRealtime, type LiveStatus } from "@/lib/realtime";
import { cn } from "@/lib/utils";

export interface AppNotification {
  id: string;
  kind: string;
  severity: "info" | "warning" | "critical";
  title: string;
  body: string | null;
  link: string | null;
  created_at: string;
  unread: boolean;
}

interface NotificationList {
  items: AppNotification[];
  unread_count: number;
}

const SEVERITY_ICON = {
  info: { icon: Info, className: "text-series-1" },
  warning: { icon: AlertTriangle, className: "text-status-warning" },
  critical: { icon: OctagonAlert, className: "text-status-critical" },
} as const;

export function NotificationCenter() {
  const { restaurantId } = useAuth();
  const queryClient = useQueryClient();
  const list = useApi<NotificationList>(["notifications"], restaurantId ? "/notifications" : null);
  // Items unread when the menu opened stay highlighted until it closes.
  const [highlighted, setHighlighted] = useState<Set<string>>(new Set());
  const unread = list.data?.unread_count ?? 0;

  const onOpenChange = (open: boolean) => {
    if (!open) {
      setHighlighted(new Set());
      return;
    }
    const ids = new Set((list.data?.items ?? []).filter((n) => n.unread).map((n) => n.id));
    setHighlighted(ids);
    if (unread > 0) {
      void api("/notifications/read", { method: "POST" })
        .then(() =>
          queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === restaurantId && q.queryKey[1] === "notifications" }),
        )
        .catch(() => {
          // Leave the badge as it is; the next refresh retries.
        });
    }
  };

  return (
    <DropdownMenu onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        >
          <Bell />
          {unread > 0 ? (
            <span className="absolute top-1 right-1 flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] leading-4 font-semibold text-white tabular-nums">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(22rem,calc(100vw-2rem))] p-0">
        <DropdownMenuLabel className="flex items-center justify-between px-3 py-2.5">
          <span className="text-sm font-semibold">Notifications</span>
          {highlighted.size > 0 ? (
            <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
              <CheckCheck className="size-3.5" aria-hidden /> Marked as read
            </span>
          ) : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="m-0" />
        <div className="max-h-[min(28rem,70dvh)] overflow-y-auto py-1">
          {list.isLoading ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">Loading…</p>
          ) : list.isError ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">Notifications could not be loaded.</p>
          ) : !list.data?.items.length ? (
            <div className="px-3 py-8 text-center">
              <Bell className="mx-auto mb-2 size-6 text-muted-foreground/60" aria-hidden />
              <p className="text-sm font-medium">You&apos;re all caught up</p>
              <p className="text-xs text-muted-foreground">Stock alerts, deliveries and reorder suggestions appear here.</p>
            </div>
          ) : (
            list.data.items.map((n) => {
              const { icon: Icon, className } = SEVERITY_ICON[n.severity] ?? SEVERITY_ICON.info;
              const content = (
                <>
                  <Icon className={cn("mt-0.5 size-4 shrink-0", className)} aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-start justify-between gap-2">
                      <span className="text-sm leading-snug font-medium">{n.title}</span>
                      {highlighted.has(n.id) ? (
                        <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-label="New" />
                      ) : null}
                    </span>
                    {n.body ? <span className="mt-0.5 block text-xs text-muted-foreground">{n.body}</span> : null}
                    <time dateTime={n.created_at} className="mt-1 block text-[11px] text-muted-foreground/80">
                      {formatRelativeTime(n.created_at)}
                    </time>
                  </span>
                </>
              );
              const itemClass = cn("mx-1 items-start gap-3 rounded-md px-2 py-2.5", highlighted.has(n.id) && "bg-accent/50");
              return n.link ? (
                <DropdownMenuItem key={n.id} asChild className={itemClass}>
                  <Link href={n.link}>{content}</Link>
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem key={n.id} className={itemClass}>
                  {content}
                </DropdownMenuItem>
              );
            })
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const STATUS_COPY: Record<LiveStatus, { label: string; hint: string; dot: string }> = {
  live: { label: "Live", hint: "Receiving updates as they happen", dot: "bg-status-good" },
  polling: { label: "Live", hint: "Receiving updates every few seconds (streaming unavailable)", dot: "bg-status-good" },
  connecting: { label: "Connecting", hint: "Connecting to live updates…", dot: "bg-status-warning animate-pulse" },
  offline: { label: "Offline", hint: "Cannot reach the server. Data on screen may be out of date.", dot: "bg-destructive" },
};

export function LiveStatusIndicator() {
  const { status } = useRealtime();
  const { restaurantId } = useAuth();
  if (!restaurantId) return null;
  const copy = STATUS_COPY[status];
  return (
    <span
      role="status"
      title={copy.hint}
      className="hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium text-muted-foreground sm:inline-flex"
    >
      <span className={cn("size-2 rounded-full", copy.dot)} aria-hidden />
      {copy.label}
      <span className="sr-only">: {copy.hint}</span>
    </span>
  );
}
