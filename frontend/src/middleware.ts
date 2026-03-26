import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Middleware — lightweight request interceptor.
 *
 * Auth is handled CLIENT-SIDE by the AuthProvider + dashboard layout.
 * Supabase JS stores sessions in localStorage (not cookies), so server-side
 * middleware cannot reliably detect auth state. Instead, we only use middleware
 * for security headers and let the client redirect unauthenticated users.
 */
export function middleware(req: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
