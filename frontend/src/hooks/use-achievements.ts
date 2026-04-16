/**
 * Achievement / Badge unlock system.
 *
 * Watches the user's live data and fires a callback when a new milestone is
 * crossed. Achievements are persisted in localStorage so they are only shown
 * once per user.
 */
"use client";

import { useCallback, useEffect, useRef } from "react";

export interface Achievement {
  id: string;
  title: string;
  description: string;
  emoji: string;
  xp: number;
}

const ALL_ACHIEVEMENTS: Achievement[] = [
  { id: "first_app",        title: "First Step",       description: "Created your first application",             emoji: "🚀", xp: 50  },
  { id: "five_apps",        title: "Job Hunter",       description: "Created 5 applications",                     emoji: "🎯", xp: 100 },
  { id: "ten_apps",         title: "On the Grind",     description: "Created 10 applications",                    emoji: "💪", xp: 200 },
  { id: "first_evidence",   title: "Proof Builder",    description: "Added your first proof item",                emoji: "🏅", xp: 30  },
  { id: "five_evidence",    title: "Evidence Pro",     description: "Built a 5-item proof library",               emoji: "📂", xp: 75  },
  { id: "twenty_evidence",  title: "Proof Champion",   description: "Amassed 20+ proof items",                    emoji: "🏆", xp: 150 },
  { id: "streak_3",         title: "On a Roll",        description: "3-day learning streak",                      emoji: "🔥", xp: 60  },
  { id: "streak_7",         title: "Streak Master",    description: "7-day learning streak",                      emoji: "⚡", xp: 150 },
  { id: "profile_complete", title: "Identity Set",     description: "Profile completeness reached 80%+",         emoji: "✨", xp: 100 },
  { id: "ats_90",           title: "ATS Champion",     description: "Achieved an ATS score of 90+",              emoji: "🎖️", xp: 120 },
  { id: "high_match",       title: "Perfect Match",    description: "Got a job match score of 90+",              emoji: "💯", xp: 100 },
];

function storageKey(userId: string) {
  return `hs_achievements_${userId}`;
}

function getUnlocked(userId: string): Set<string> {
  try {
    const raw = localStorage.getItem(storageKey(userId));
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

function saveUnlocked(userId: string, ids: Set<string>) {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify([...ids]));
  } catch {
    // localStorage may be unavailable in SSR or private mode
  }
}

export interface AchievementInput {
  userId: string;
  appCount: number;
  evidenceCount: number;
  streak: number;
  profilePct: number;
  /** best ATS score across all apps */
  bestAtsScore?: number;
  /** best match score across all apps */
  bestMatchScore?: number;
  onUnlock: (achievement: Achievement) => void;
}

export function useAchievements({
  userId,
  appCount,
  evidenceCount,
  streak,
  profilePct,
  bestAtsScore = 0,
  bestMatchScore = 0,
  onUnlock,
}: AchievementInput) {
  // Keep stable ref to callback to avoid stale closure issues
  const onUnlockRef = useRef(onUnlock);
  onUnlockRef.current = onUnlock;

  const check = useCallback(() => {
    if (!userId || typeof window === "undefined") return;
    const unlocked = getUnlocked(userId);
    const newlyUnlocked: Achievement[] = [];

    const conditions: Record<string, boolean> = {
      first_app:        appCount >= 1,
      five_apps:        appCount >= 5,
      ten_apps:         appCount >= 10,
      first_evidence:   evidenceCount >= 1,
      five_evidence:    evidenceCount >= 5,
      twenty_evidence:  evidenceCount >= 20,
      streak_3:         streak >= 3,
      streak_7:         streak >= 7,
      profile_complete: profilePct >= 80,
      ats_90:           bestAtsScore >= 90,
      high_match:       bestMatchScore >= 90,
    };

    for (const ach of ALL_ACHIEVEMENTS) {
      if (!unlocked.has(ach.id) && conditions[ach.id]) {
        newlyUnlocked.push(ach);
        unlocked.add(ach.id);
      }
    }

    if (newlyUnlocked.length > 0) {
      saveUnlocked(userId, unlocked);
      // Stagger notifications so multiple unlocks don't stack immediately
      newlyUnlocked.forEach((a, i) => {
        setTimeout(() => onUnlockRef.current(a), i * 1200);
      });
    }
  }, [userId, appCount, evidenceCount, streak, profilePct, bestAtsScore, bestMatchScore]);

  useEffect(() => {
    // Slight delay so data is stable before checking
    const t = setTimeout(check, 500);
    return () => clearTimeout(t);
  }, [check]);
}

export { ALL_ACHIEVEMENTS };
