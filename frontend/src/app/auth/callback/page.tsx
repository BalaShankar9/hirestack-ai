"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { AlertCircle, RefreshCw } from "lucide-react";

/**
 * OAuth callback route — Supabase redirects here after social sign-in.
 * Exchanges the URL hash/params for a session, then redirects to dashboard.
 *
 * Handles: success, explicit errors, and stale/timeout scenarios.
 */

const TIMEOUT_MS = 15_000;

export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 1. Check if the URL contains an explicit error from the OAuth provider
    const params = new URLSearchParams(window.location.search);
    const hashParams = new URLSearchParams(
      window.location.hash.replace(/^#/, "")
    );
    const urlError =
      params.get("error_description") ||
      hashParams.get("error_description") ||
      params.get("error") ||
      hashParams.get("error");

    if (urlError) {
      setError(decodeURIComponent(urlError));
      return;
    }

    // 2. Listen for auth state change → redirect on success
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") {
        router.replace("/dashboard");
      }
    });

    // 3. Timeout fallback — if nothing happens within 15 s, show error
    const timeout = setTimeout(() => {
      setError(
        "Sign-in is taking too long. The provider may not have responded."
      );
    }, TIMEOUT_MS);

    return () => {
      subscription.unsubscribe();
      clearTimeout(timeout);
    };
  }, [router]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex max-w-sm flex-col items-center gap-4 text-center px-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
            <AlertCircle className="h-6 w-6 text-destructive" />
          </div>
          <h2 className="text-lg font-semibold">Sign-in failed</h2>
          <p className="text-sm text-muted-foreground">{error}</p>
          <div className="flex gap-3 mt-2">
            <button
              onClick={() => router.replace("/login")}
              className="inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
            >
              Back to Login
            </button>
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-muted-foreground text-sm">Completing sign-in…</p>
      </div>
    </div>
  );
}
