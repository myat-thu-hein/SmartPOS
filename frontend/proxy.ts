import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// A UX convenience only: unauthenticated visitors are sent to the login page.
// Real authentication and authorisation are enforced by the backend API.
const PUBLIC_PATHS = ["/login", "/forgot-password", "/reset-password"];
const SESSION_COOKIE = "smartpos_session";

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  const hasSession = request.cookies.has(SESSION_COOKIE);
  if (!isPublic && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|robots\\.txt|.*\\.(?:png|svg|ico|webp|woff2?)$).*)"],
};
