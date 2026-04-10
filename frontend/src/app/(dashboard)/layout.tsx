"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/components/providers";
import { AppShell } from "@/components/app-shell";
import { PageTransition } from "@/components/page-transition";
import { OnboardingProvider } from "@/contexts/onboarding-context";
import api from "@/lib/api";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, session, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [hasRedirected, setHasRedirected] = useState(false);

  /* Keep the API client token in sync with the session */
  useEffect(() => {
    if (session?.access_token) {
      api.setToken(session.access_token);
    } else {
      api.setToken(null);
    }
  }, [session]);

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
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <OnboardingProvider>
      <AppShell>
        <PageTransition>{children}</PageTransition>
      </AppShell>
    </OnboardingProvider>
  );
}
