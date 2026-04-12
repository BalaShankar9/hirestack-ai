"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { supabase } from "@/lib/supabase";

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<CallbackSpinner />}>
      <CallbackContent />
    </Suspense>
  );
}

/** Only allow relative paths — block open redirects. */
function sanitizeReturnTo(raw: string | null): string {
  if (!raw) return "/dashboard";
  const trimmed = raw.trim();
  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) return trimmed;
  return "/dashboard";
}

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") {
        const raw =
          searchParams.get("returnTo") ||
          (typeof sessionStorage !== "undefined"
            ? sessionStorage.getItem("hirestack_return_to")
            : null);

        if (typeof sessionStorage !== "undefined") {
          sessionStorage.removeItem("hirestack_return_to");
        }

        router.replace(sanitizeReturnTo(raw));
      }
    });

    // Timeout — if sign-in doesn't complete in 15s, show error
    const timer = setTimeout(() => setTimedOut(true), 15_000);

    return () => {
      subscription.unsubscribe();
      clearTimeout(timer);
    };
  }, [router, searchParams]);

  if (timedOut) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-3 max-w-sm text-center">
          <p className="text-sm font-medium">Sign-in is taking too long</p>
          <p className="text-muted-foreground text-xs">
            Please try again. If the problem persists, clear your browser cookies and retry.
          </p>
          <button
            className="mt-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
            onClick={() => router.replace("/login")}
          >
            Back to login
          </button>
        </div>
      </div>
    );
  }

  return <CallbackSpinner />;
}

function CallbackSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-muted-foreground text-sm">Completing sign-in…</p>
      </div>
    </div>
  );
}
