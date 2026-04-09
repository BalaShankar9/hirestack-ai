"use client";

import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/providers";

/**
 * Onboarding state tracks where a user is in the product journey.
 * Stages:
 *   - "new"      → No applications yet. Show guided first-run experience.
 *   - "started"  → Has started but not completed first application.
 *   - "active"   → Has at least one completed application. Full experience.
 */
export type OnboardingStage = "new" | "started" | "active";

interface OnboardingState {
  stage: OnboardingStage;
  loading: boolean;
  /**
   * Number of completed applications.
   * Used to decide which features to emphasize.
   */
  applicationCount: number;
  /** Has the user set up their profile? */
  hasProfile: boolean;
  /** Has the user added any evidence? */
  hasEvidence: boolean;
  /** Mark stage manually (e.g. after first app creation) */
  setStage: (stage: OnboardingStage) => void;
  /** Update counts to re-evaluate stage */
  updateCounts: (counts: { applications?: number; hasProfile?: boolean; hasEvidence?: boolean }) => void;
}

const OnboardingContext = createContext<OnboardingState>({
  stage: "new",
  loading: true,
  applicationCount: 0,
  hasProfile: false,
  hasEvidence: false,
  setStage: () => {},
  updateCounts: () => {},
});

export function useOnboarding() {
  return useContext(OnboardingContext);
}

export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [applicationCount, setApplicationCount] = useState(0);
  const [hasProfile, setHasProfile] = useState(false);
  const [hasEvidence, setHasEvidence] = useState(false);
  const [manualStage, setManualStage] = useState<OnboardingStage | null>(null);

  // Derive stage from data
  const stage: OnboardingStage = useMemo(() => {
    if (manualStage) return manualStage;
    if (applicationCount > 0) return "active";
    return "new";
  }, [applicationCount, manualStage]);

  // Load onboarding state from localStorage (fast) then optionally from backend
  useEffect(() => {
    if (!user) {
      setLoading(false);
      return;
    }

    const stored = localStorage.getItem(`hirestack_onboarding_${user.uid}`);
    if (stored) {
      try {
        const data = JSON.parse(stored);
        setApplicationCount(data.applicationCount ?? 0);
        setHasProfile(data.hasProfile ?? false);
        setHasEvidence(data.hasEvidence ?? false);
      } catch {}
    }
    setLoading(false);
  }, [user]);

  // Persist changes
  useEffect(() => {
    if (!user) return;
    localStorage.setItem(
      `hirestack_onboarding_${user.uid}`,
      JSON.stringify({ applicationCount, hasProfile, hasEvidence })
    );
  }, [user, applicationCount, hasProfile, hasEvidence]);

  const updateCounts = React.useCallback(
    (counts: { applications?: number; hasProfile?: boolean; hasEvidence?: boolean }) => {
      if (counts.applications !== undefined) setApplicationCount(counts.applications);
      if (counts.hasProfile !== undefined) setHasProfile(counts.hasProfile);
      if (counts.hasEvidence !== undefined) setHasEvidence(counts.hasEvidence);
      // Clear manual override when data changes
      setManualStage(null);
    },
    []
  );

  const value = useMemo(
    () => ({
      stage,
      loading,
      applicationCount,
      hasProfile,
      hasEvidence,
      setStage: setManualStage,
      updateCounts,
    }),
    [stage, loading, applicationCount, hasProfile, hasEvidence, updateCounts]
  );

  return (
    <OnboardingContext.Provider value={value}>
      {children}
    </OnboardingContext.Provider>
  );
}
