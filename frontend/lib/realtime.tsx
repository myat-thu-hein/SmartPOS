"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, buildUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** One entry of the backend's live-update feed (see backend/app/services/realtime.py). */
export interface LiveEvent {
  id: number;
  type: string;
  topic: string;
  entity_id: string | null;
  data: Record<string, unknown>;
  actor_user_id: string | null;
  created_at: string;
}

export type LiveStatus = "connecting" | "live" | "polling" | "offline";

interface RealtimeValue {
  status: LiveStatus;
  /** Listen to every event; returns an unsubscribe function. */
  subscribe: (listener: (event: LiveEvent) => void) => () => void;
}

const RealtimeContext = createContext<RealtimeValue>({ status: "offline", subscribe: () => () => {} });

/** Which cached queries (by the key segment after the restaurant id) each topic makes stale. */
export const TOPIC_QUERIES: Record<string, string[]> = {
  order: ["orders", "order", "kitchen", "tables", "dashboard", "customers", "customer", "analytics", "payments", "insights"],
  table: ["tables", "dashboard"],
  stock: ["ingredients", "inventory", "movements", "dashboard", "recipes", "recipe", "insights"],
  po: ["purchase-orders", "purchase-order", "ingredients", "inventory", "dashboard", "suppliers"],
  supplier: ["suppliers"],
  recommendations: ["recommendations", "dashboard"],
  forecast: ["forecast", "dashboard", "recommendations", "insights"],
  menu: ["products", "categories", "modifiers", "recipes", "recipe"],
  settings: ["restaurant", "payment-methods", "discounts"],
  customer: ["customers", "customer"],
  notification: ["notifications"],
};

const POLL_MS = 3_000;
const RETRY_STREAM_MS = 60_000;
const FAILURES_BEFORE_POLLING = 3;

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const { restaurantId, me } = useAuth();
  const userId = me?.user.id;
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const listeners = useRef(new Set<(event: LiveEvent) => void>());

  useEffect(() => {
    if (!restaurantId || !userId) return;
    let stopped = false;
    let cursor: number | null = null;
    let source: EventSource | null = null;
    let failures = 0;
    let wasDisconnected = false;
    let polling = 0; // generation of the active polling loop; 0 = not polling
    let generations = 0;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let flushTimer: ReturnType<typeof setTimeout> | undefined;
    const stale = new Set<string>();

    // Batch refreshes so a burst of events causes one refetch per query.
    const flush = () => {
      flushTimer = undefined;
      const keys = new Set(stale);
      stale.clear();
      void queryClient.invalidateQueries({
        predicate: (q) => q.queryKey[0] === restaurantId && keys.has(String(q.queryKey[1])),
      });
    };
    const resyncAll = () =>
      void queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === restaurantId });

    const handle = (event: LiveEvent) => {
      cursor = Math.max(cursor ?? 0, event.id);
      for (const key of TOPIC_QUERIES[event.topic] ?? []) stale.add(key);
      flushTimer ??= setTimeout(flush, 250);
      listeners.current.forEach((listener) => listener(event));
    };

    const stopPolling = () => {
      polling = 0;
      clearTimeout(pollTimer);
    };

    const connectStream = () => {
      if (stopped) return;
      if (typeof EventSource === "undefined") return startPolling();
      stopPolling();
      setStatus("connecting");
      const query = { restaurant_id: restaurantId, after: cursor ?? undefined };
      source = new EventSource(buildUrl("/events/stream", query), { withCredentials: true });
      source.addEventListener("ready", (message) => {
        failures = 0;
        setStatus("live");
        if (cursor === null) cursor = Number((message as MessageEvent).lastEventId) || 0;
        // After an outage, refresh everything once in case events were missed.
        if (wasDisconnected) resyncAll();
        wasDisconnected = false;
      });
      source.onmessage = (message) => {
        try {
          handle(JSON.parse(message.data) as LiveEvent);
        } catch {
          // Ignore malformed frames; the next event or resync recovers.
        }
      };
      source.onerror = () => {
        if (stopped) return;
        // A stream that ends normally also fires "error" and then reconnects by itself.
        // A refused stream (an error response, e.g. backend down or signed out) is CLOSED
        // and never retried by the browser, so switch to polling straight away.
        failures += 1;
        const closed = source?.readyState === EventSource.CLOSED;
        if (closed || failures >= FAILURES_BEFORE_POLLING) {
          source?.close();
          source = null;
          wasDisconnected = true;
          startPolling();
          clearTimeout(retryTimer);
          retryTimer = setTimeout(connectStream, RETRY_STREAM_MS);
        } else if (failures > 1) {
          // One error is the routine end of a stream; only report repeated failures.
          setStatus("connecting");
        }
      };
    };

    // Fallback transport: ask for events after the cursor every few seconds.
    const startPolling = () => {
      stopPolling();
      const generation = ++generations;
      polling = generation;
      const poll = async () => {
        if (stopped || polling !== generation) return;
        try {
          const page = await api<{ events: LiveEvent[]; cursor: number }>("/events", {
            query: { after: cursor ?? undefined },
          });
          if (stopped || polling !== generation) return;
          if (cursor === null) cursor = page.cursor;
          else page.events.forEach(handle);
          cursor = Math.max(cursor, page.cursor);
          setStatus("polling");
          if (wasDisconnected) resyncAll();
          wasDisconnected = false;
        } catch {
          if (stopped || polling !== generation) return;
          setStatus("offline");
          wasDisconnected = true;
        }
        pollTimer = setTimeout(poll, document.visibilityState === "hidden" ? POLL_MS * 5 : POLL_MS);
      };
      void poll();
    };

    connectStream();
    return () => {
      stopped = true;
      source?.close();
      stopPolling();
      clearTimeout(retryTimer);
      if (flushTimer) clearTimeout(flushTimer);
    };
  }, [restaurantId, userId, queryClient]);

  const subscribe = useCallback((listener: (event: LiveEvent) => void) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);
  const value = useMemo<RealtimeValue>(() => ({ status, subscribe }), [status, subscribe]);
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime(): RealtimeValue {
  return useContext(RealtimeContext);
}

/** Run a callback for live events, e.g. to show a toast. */
export function useLiveEvents(listener: (event: LiveEvent) => void) {
  const { subscribe } = useRealtime();
  const latest = useRef(listener);
  useEffect(() => {
    latest.current = listener;
  });
  useEffect(() => subscribe((event) => latest.current(event)), [subscribe]);
}

/**
 * refetchInterval for screens that must stay current: rely on live events when
 * they are flowing (with a slow safety refresh), and poll quickly when not.
 */
export function useLiveRefetchInterval(fallbackMs: number, safetyMs = 120_000): number {
  const { status } = useRealtime();
  return status === "live" || status === "polling" ? safetyMs : fallbackMs;
}
