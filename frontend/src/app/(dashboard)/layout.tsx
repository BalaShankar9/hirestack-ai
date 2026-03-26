"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/providers";
import { AppShell } from "@/components/app-shell";
import { QuotaProvider } from "@/contexts/quota-context";
import api from "@/lib/api";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, session, loading } = useAuth();
  const router = useRouter();

  /* Keep the API client token in sync with the session */
  useEffect(() => {
    if (session?.access_token) {
      api.setToken(session.access_token);
    } else {
      api.setToken(null);
    }
  }, [session]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <QuotaProvider>
      <AppShell>{children}</AppShell>
    </QuotaProvider>
  );
}
