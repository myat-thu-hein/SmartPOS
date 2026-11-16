// @vitest-environment node
import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/v1/[...path]/route";

function request(path: string): NextRequest {
  const req = new Request(`https://smartpos.example${path}`) as Request & {
    nextUrl: URL;
  };
  req.nextUrl = new URL(req.url);
  return req as unknown as NextRequest;
}

describe("/api/v1 proxy", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("explains a Vercel deployment that has no API instead of failing vaguely", async () => {
    vi.stubEnv("VERCEL", "1");
    vi.stubEnv("BACKEND_URL", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const response = await GET(request("/api/v1/auth/demo"));
    expect(response.status).toBe(503);
    const body = await response.json();
    expect(body.error.code).toBe("api_not_deployed");
    expect(body.error.message).toContain("Root Directory");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards to BACKEND_URL otherwise, keeping the path and query", async () => {
    vi.stubEnv("VERCEL", "");
    vi.stubEnv("BACKEND_URL", "http://api.internal:8000/");
    const fetchSpy = vi.fn().mockResolvedValue(new Response('{"status":"ok"}', { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);
    const response = await GET(request("/api/v1/health?x=1"));
    expect(response.status).toBe(200);
    expect(fetchSpy.mock.calls[0][0]).toBe("http://api.internal:8000/api/v1/health?x=1");
  });
});
