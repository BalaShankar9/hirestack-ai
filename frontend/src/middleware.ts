import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Routes that don't require authentication
// Guest mode: /new is public so anyone can try 1 free application
const PUBLIC_PATHS = ["/login", "/auth/callback", "/auth/reset-password", "/new"];
const PUBLIC_PREFIXES = ["/_next/", "/api/", "/favicon", "/review/", "/applications/"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Allow public routes
  if (PUBLIC_PATHS.includes(pathname)) return NextResponse.next();
  if (PUBLIC_PREFIXES.some((p) => pathname.startsWith(p))) return NextResponse.next();

  // Check for Supabase auth cookie (sb-*-auth-token)
  const cookies = req.cookies.getAll();
  const hasAuthCookie = cookies.some(
    (c) => c.name.includes("-auth-token") || c.name.includes("sb-")
  );

  if (!hasAuthCookie) {
    const loginUrl = new URL("/login", req.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
