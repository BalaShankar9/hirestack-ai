"use client";

import { useEffect } from "react";
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

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") {
        // Check for returnTo param or sessionStorage
        const returnTo =
          searchParams.get("returnTo") ||
          (typeof sessionStorage !== "undefined"
            ? sessionStorage.getItem("hirestack_return_to")
            : null) ||
          "/dashboard";

        if (typeof sessionStorage !== "undefined") {
          sessionStorage.removeItem("hirestack_return_to");
        }

        router.replace(returnTo);
      }
    });
  }, [router, searchParams]);

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
