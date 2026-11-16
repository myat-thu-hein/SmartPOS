import type { NextRequest } from "next/server";

/**
 * Same-origin proxy from the browser to the FastAPI backend, used by `next dev`,
 * Docker and any host where Next.js serves /api/v1 itself.
 *
 * On Vercel, vercel.json routes /api/v1/* straight to the FastAPI service, so a
 * request only reaches this handler there when the API was not deployed (for
 * example the project's Root Directory is `frontend`). It then explains how to
 * fix the project instead of failing with a generic error.
 *
 * BACKEND_URL is read on every request rather than at build time, so a Docker
 * image can be pointed at another backend without rebuilding. Keeping the API
 * on the frontend's origin also keeps session cookies first-party.
 */

// Long enough for the live-updates stream; clients reconnect when it ends.
export const maxDuration = 300;

// Hop-by-hop headers (RFC 9110 §7.6.1) and headers this proxy sets itself.
const DROP_REQUEST_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  "accept-encoding",
  "x-forwarded-for",
  "x-forwarded-host",
  "x-forwarded-proto",
  "x-real-ip",
]);
// fetch() already decoded the body, so the upstream encoding and length no longer apply.
const DROP_RESPONSE_HEADERS = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
  "set-cookie",
]);

function backendBase(): string {
  return (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

function clientIp(request: NextRequest): string | null {
  // Vercel and most reverse proxies put the original client first.
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return forwarded || request.headers.get("x-real-ip");
}

function apiError(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message, details: null, request_id: null } }, { status });
}

async function proxy(request: NextRequest): Promise<Response> {
  if (process.env.VERCEL && !process.env.BACKEND_URL) {
    return apiError(
      503,
      "api_not_deployed",
      "This deployment contains only the website, not the SmartPOS API. In Vercel, open the project's " +
        "Settings → Build and Deployment, clear Root Directory (use the repository root) and set Framework " +
        "Preset to Services, so vercel.json deploys both parts, then redeploy.",
    );
  }
  const target = `${backendBase()}${request.nextUrl.pathname}${request.nextUrl.search}`;
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!DROP_REQUEST_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  });
  const ip = clientIp(request);
  if (ip) headers.set("x-forwarded-for", ip);
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));
  headers.set("x-forwarded-host", request.headers.get("host") ?? request.nextUrl.host);

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
      // Stop the backend request (e.g. the live-updates stream) when the browser goes away.
      signal: request.signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") return new Response(null, { status: 499 });
    return apiError(
      502,
      "backend_unreachable",
      "The SmartPOS API is not reachable. Check that the backend is running and BACKEND_URL is correct.",
    );
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!DROP_RESPONSE_HEADERS.has(key.toLowerCase())) responseHeaders.set(key, value);
  });
  // Several cookies (session + CSRF) must stay separate headers.
  for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append("set-cookie", cookie);
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
