// Small fetch wrapper for the SmartPOS API.
//
// * Requests go to the same origin (/api/v1/...), proxied to the backend by
//   Next.js, so the httpOnly session cookie is sent automatically.
// * State-changing requests echo the CSRF token from the readable cookie.
// * The active restaurant is sent in X-Restaurant-ID; the backend verifies it.

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
const CSRF_COOKIE = "smartpos_csrf";
const RESTAURANT_KEY = "smartpos.restaurantId";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  requestId?: string;

  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  /** Field-level validation messages, keyed by field path. */
  get fieldErrors(): Record<string, string> {
    if (!Array.isArray(this.details)) return {};
    const out: Record<string, string> = {};
    for (const d of this.details as { field?: string | null; message?: string }[]) {
      if (d.field && d.message && !out[d.field]) out[d.field] = d.message;
    }
    return out;
  }
}

let restaurantId: string | null = null;
const unauthorizedListeners = new Set<() => void>();

export function setRestaurantId(id: string | null) {
  restaurantId = id;
  try {
    if (id) window.localStorage.setItem(RESTAURANT_KEY, id);
    else window.localStorage.removeItem(RESTAURANT_KEY);
  } catch {
    // Storage may be unavailable (private mode); the in-memory value still works.
  }
}

export function getStoredRestaurantId(): string | null {
  try {
    return window.localStorage.getItem(RESTAURANT_KEY);
  } catch {
    return null;
  }
}

export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

export function newIdempotencyKey(prefix = "web"): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${random}`;
}

type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  idempotencyKey?: string;
  signal?: AbortSignal;
  /** Skip the X-Restaurant-ID header (auth and platform endpoints). */
  noRestaurant?: boolean;
}

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)));
    else params.set(key, String(value));
  }
  const qs = params.toString();
  return `${API_BASE}/api/v1${path}${qs ? `?${qs}` : ""}`;
}

async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (!options.noRestaurant && restaurantId) headers["X-Restaurant-ID"] = restaurantId;
  if (method !== "GET") {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      credentials: "include",
      signal: options.signal,
      cache: "no-store",
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "Cannot reach the SmartPOS server. Check your connection.");
  }
  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed (${response.status}).`;
    let details: unknown;
    let requestId: string | undefined;
    try {
      const body = await response.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
      details = body?.error?.details;
      requestId = body?.error?.request_id;
    } catch {
      // Non-JSON error body (e.g. proxy error page).
    }
    if (response.status === 401 && !path.startsWith("/auth/login")) {
      unauthorizedListeners.forEach((l) => l());
    }
    throw new ApiError(response.status, code, message, details, requestId);
  }
  return response;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Download a file (CSV report) using the authenticated session. */
export async function downloadFile(path: string, query: Query, fallbackName: string): Promise<void> {
  const response = await request(path, { query });
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoking synchronously can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
