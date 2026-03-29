"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/providers";
import { AppShell } from "@/components/app-shell";
import { PageTransition } from "@/components/page-transition";
import { QuotaProvider } from "@/contexts/quota-context";
import api from "@/lib/api";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, session, loading } = useAuth();
  const router = useRouter();
  const hasRendered = useRef(false);

  /* Keep the API client token in sync with the session */
  useEffect(() => {
    if (session?.access_token) {
      api.setToken(session.access_token);
    } else {
      api.setToken(null);
    }
  }, [session]);

  // Only show loading spinner on first mount, never re-show it
  // (re-showing unmounts children and destroys form state)
  if (loading && !hasRendered.current) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  hasRendered.current = true;

  return (
    <QuotaProvider>
      <AppShell>
        <PageTransition>{children}</PageTransition>
      </AppShell>
    </QuotaProvider>
  );
}
