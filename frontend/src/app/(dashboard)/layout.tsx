"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/components/providers";
import { AppShell } from "@/components/app-shell";
import { PageTransition } from "@/components/page-transition";
import { OnboardingProvider } from "@/contexts/onboarding-context";
import { LiveAgentActivityDock } from "@/components/agents/live-agent-activity-dock";
import api from "@/lib/api";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, session, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [hasRedirected, setHasRedirected] = useState(false);
  const [authTimedOut, setAuthTimedOut] = useState(false);

  /* Keep the API client token in sync with the session */
  useEffect(() => {
    if (session?.access_token) {
      api.setToken(session.access_token);
    } else {
      api.setToken(null);
    }
  }, [session]);

  /* Safety timeout: if auth stays in loading state > 10s, show recovery UI */
  useEffect(() => {
    if (!loading) {
      setAuthTimedOut(false);
      return;
    }
    const t = setTimeout(() => setAuthTimedOut(true), 10_000);
    return () => clearTimeout(t);
  }, [loading]);

  useEffect(() => {
    if (!loading && !user && !hasRedirected) {
      setHasRedirected(true);
      if (pathname === "/new") {
        window.location.assign("/login?mode=register&redirect=/new");
      } else {
        const currentPath = pathname || "/dashboard";
        window.location.assign("/login?redirect=" + encodeURIComponent(currentPath));
      }
    }
  }, [user, loading, pathname, hasRedirected]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        {authTimedOut && (
          <div className="flex flex-col items-center gap-2 text-center px-4">
            <p className="text-sm text-muted-foreground">
              Taking longer than expected…
            </p>
            <button
              onClick={() => window.location.reload()}
              className="text-sm font-medium text-primary underline underline-offset-2 hover:text-primary/80"
            >
              Refresh the page
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <OnboardingProvider>
      <AppShell>
        <PageTransition>{children}</PageTransition>
      </AppShell>
      <LiveAgentActivityDock />
    </OnboardingProvider>
  );
}
