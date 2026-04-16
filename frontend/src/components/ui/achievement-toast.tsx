"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import type { Achievement } from "@/hooks/use-achievements";
import { cn } from "@/lib/utils";

interface AchievementToastProps {
  achievement: Achievement | null;
  onDismiss: () => void;
}

export function AchievementToast({ achievement, onDismiss }: AchievementToastProps) {
  useEffect(() => {
    if (!achievement) return;
    const t = setTimeout(onDismiss, 5000);
    return () => clearTimeout(t);
  }, [achievement, onDismiss]);

  return (
    <AnimatePresence>
      {achievement && (
        <motion.div
          initial={{ opacity: 0, y: 60, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 40, scale: 0.9 }}
          transition={{ type: "spring", stiffness: 400, damping: 28 }}
          className={cn(
            "fixed bottom-6 right-6 z-[200] flex items-center gap-3",
            "rounded-2xl border border-amber-500/30 bg-card shadow-2xl px-4 py-3",
            "max-w-xs backdrop-blur-sm",
          )}
        >
          {/* Glow ring */}
          <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-amber-500/10 to-orange-500/5 pointer-events-none" />

          {/* Badge emoji */}
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/10 text-2xl">
            {achievement.emoji}
          </div>

          {/* Text */}
          <div className="flex-1 min-w-0 relative">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-amber-500">
              Achievement Unlocked
            </p>
            <p className="text-sm font-bold truncate">{achievement.title}</p>
            <p className="text-[11px] text-muted-foreground truncate">{achievement.description}</p>
            <p className="text-[10px] text-amber-500/80 font-semibold mt-0.5">+{achievement.xp} XP</p>
          </div>

          {/* Dismiss */}
          <button
            type="button"
            aria-label="Dismiss"
            onClick={onDismiss}
            className="shrink-0 text-muted-foreground hover:text-foreground transition-colors relative"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
