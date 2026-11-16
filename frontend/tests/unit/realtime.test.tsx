import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const RID = "rest-1";
const apiMock = vi.fn();
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ restaurantId: RID, me: { user: { id: "user-1" } } }) }));
vi.mock("@/lib/api", () => ({
  api: (...args: unknown[]) => apiMock(...args),
  buildUrl: (path: string, query: Record<string, unknown>) =>
    `/api/v1${path}?${new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined) as [string, string][])}`,
}));

/** Minimal EventSource double the tests drive by hand. */
class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];
  readyState = FakeEventSource.CONNECTING;
  onmessage: ((m: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  listeners: Record<string, ((m: MessageEvent) => void)[]> = {};
  closed = false;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (m: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }
  ready(cursor: number) {
    this.readyState = FakeEventSource.OPEN;
    this.listeners.ready?.forEach((fn) => fn(new MessageEvent("ready", { data: "{}", lastEventId: String(cursor) })));
  }
  send(event: object) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(event) }));
  }
  fail(closed: boolean) {
    this.readyState = closed ? FakeEventSource.CLOSED : FakeEventSource.CONNECTING;
    this.onerror?.();
  }
}

const { RealtimeProvider, useRealtime } = await import("@/lib/realtime");

function Status() {
  return <p>status:{useRealtime().status}</p>;
}

function setup() {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <RealtimeProvider>
        <Status />
      </RealtimeProvider>
    </QueryClientProvider>,
  );
  return { client, invalidate };
}

const event = (id: number, topic: string) => ({
  id,
  type: `${topic}.changed`,
  topic,
  entity_id: null,
  data: {},
  actor_user_id: null,
  created_at: new Date().toISOString(),
});

describe("RealtimeProvider", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    apiMock.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("goes live on the stream and refreshes only the queries an event affects, batched", async () => {
    const { client, invalidate } = setup();
    const source = FakeEventSource.instances[0];
    expect(source.url).toContain(`restaurant_id=${RID}`);
    act(() => source.ready(41));
    expect(screen.getByText("status:live")).toBeInTheDocument();

    client.setQueryData([RID, "kitchen", {}], []);
    client.setQueryData([RID, "ingredients", {}], []);
    client.setQueryData(["other-restaurant", "kitchen", {}], []);
    act(() => {
      source.send(event(42, "order"));
      source.send(event(43, "order"));
    });
    expect(invalidate).not.toHaveBeenCalled(); // batched
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(client.getQueryState([RID, "kitchen", {}])?.isInvalidated).toBe(true);
    expect(client.getQueryState([RID, "ingredients", {}])?.isInvalidated).toBe(false);
    expect(client.getQueryState(["other-restaurant", "kitchen", {}])?.isInvalidated).toBe(false);
  });

  it("falls back to polling when the stream is refused, then resumes streaming", async () => {
    apiMock.mockResolvedValue({ events: [event(8, "stock")], cursor: 8 });
    const { client } = setup();
    const source = FakeEventSource.instances[0];
    act(() => source.ready(5));
    client.setQueryData([RID, "ingredients", {}], []);

    // An error response closes the EventSource for good; the provider polls instead.
    act(() => source.fail(true));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(apiMock).toHaveBeenCalledWith("/events", { query: { after: 5 } });
    expect(screen.getByText("status:polling")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(client.getQueryState([RID, "ingredients", {}])?.isInvalidated).toBe(true);

    // Later it tries the stream again, resuming after the newest event it saw.
    await act(() => vi.advanceTimersByTimeAsync(60_000));
    const retry = FakeEventSource.instances.at(-1)!;
    expect(retry).not.toBe(source);
    expect(retry.url).toContain("after=8");
    const pollsBefore = apiMock.mock.calls.length;
    act(() => retry.ready(8));
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(apiMock.mock.calls.length).toBe(pollsBefore); // polling stopped
    expect(screen.getByText("status:live")).toBeInTheDocument();
  });

  it("treats a routine stream end as a reconnect, not an outage", () => {
    setup();
    const source = FakeEventSource.instances[0];
    act(() => source.ready(1));
    act(() => source.fail(false)); // the server ended the stream; the browser reconnects
    expect(screen.getByText("status:live")).toBeInTheDocument();
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("reports offline when polling cannot reach the server", async () => {
    apiMock.mockRejectedValue(new Error("network"));
    setup();
    act(() => FakeEventSource.instances[0].fail(true));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText("status:offline")).toBeInTheDocument();
  });
});
