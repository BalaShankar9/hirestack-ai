"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { useAuth } from "@/components/providers";
import { getPlan, isWithinLimit, type PlanTier } from "@/lib/plans";
import api from "@/lib/api";

interface QuotaState {
  plan: PlanTier;
  usage: Record<string, number>;
  loading: boolean;
}

interface QuotaContextValue extends QuotaState {
  checkQuota: (feature: string) => { allowed: boolean; remaining: number; limit: number };
  recordUsage: (feature: string) => Promise<void>;
  refresh: () => Promise<void>;
}

const QuotaContext = createContext<QuotaContextValue>({
  plan: getPlan("free"),
  usage: {},
  loading: true,
  checkQuota: () => ({ allowed: true, remaining: 999, limit: -1 }),
  recordUsage: async () => {},
  refresh: async () => {},
});

export function QuotaProvider({ children }: { children: ReactNode }) {
  const { user, session } = useAuth();
  const [state, setState] = useState<QuotaState>({
    plan: getPlan("free"),
    usage: {},
    loading: true,
  });

  const fetchQuota = useCallback(async () => {
    if (!user || !session?.access_token) {
      setState({ plan: getPlan("free"), usage: {}, loading: false });
      return;
    }
    try {
      api.setToken(session.access_token);
      const data = await api.request("/billing/status");
      const planKey = data?.plan || "free";
      setState({
        plan: getPlan(planKey),
        usage: data?.usage || {},
        loading: false,
      });
    } catch {
      setState((prev) => ({ ...prev, loading: false }));
    }
  }, [user, session?.access_token]);

  useEffect(() => {
    fetchQuota();
  }, [fetchQuota]);

  const checkQuota = useCallback(
    (feature: string) => {
      const limit = state.plan.limits[feature as keyof typeof state.plan.limits] ?? -1;
      const used = state.usage[feature] ?? 0;
      const remaining = limit === -1 ? 999 : Math.max(0, limit - used);
      return {
        allowed: isWithinLimit(used, limit),
        remaining,
        limit,
      };
    },
    [state]
  );

  const recordUsage = useCallback(
    async (feature: string) => {
      if (!user || !session?.access_token) return;
      try {
        api.setToken(session.access_token);
        await api.request("/billing/record-export", {
          method: "POST",
          body: { feature },
        });
        // Optimistic update
        setState((prev) => ({
          ...prev,
          usage: { ...prev.usage, [feature]: (prev.usage[feature] ?? 0) + 1 },
        }));
      } catch {
        // Silent — non-critical
      }
    },
    [user, session?.access_token]
  );

  return (
    <QuotaContext.Provider value={{ ...state, checkQuota, recordUsage, refresh: fetchQuota }}>
      {children}
    </QuotaContext.Provider>
  );
}

export function useQuota() {
  return useContext(QuotaContext);
}
